"""Multi-provider AI client chain for LLM routing with automatic fallback.

Build order: Groq → Gemini → OpenRouter.
Providers with missing API keys are skipped silently.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import APITimeoutError, AsyncOpenAI, NotFoundError, RateLimitError
from openai.types.chat import ChatCompletionMessageParam

LOGGER = logging.getLogger(__name__)

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_OR_FALLBACKS = 3

_THINK_CLOSED = re.compile(r"<think>[\s\S]*?</think>")
_THINK_OPEN = re.compile(r"<think>[\s\S]*$")


def strip_think_tags(raw: str) -> str:
    """Remove <think>...</think> blocks and any unclosed <think> tail from model output."""
    result = _THINK_CLOSED.sub("", raw)
    result = _THINK_OPEN.sub("", result)
    return result.strip()


@dataclass
class ProviderEntry:
    client: AsyncOpenAI
    model: str
    extra_kwargs: dict[str, Any] = field(default_factory=dict)


def _load_openrouter_fallbacks(data_dir: Path, primary: str) -> list[str]:
    path = data_dir / "free_models.json"
    try:
        with open(path) as f:
            data = json.load(f)
        candidates = [m["id"] for m in data.get("models", []) if m.get("enabled", False)]
        fallbacks = [m for m in candidates if m != primary][:_MAX_OR_FALLBACKS]
        LOGGER.info("Loaded %d OpenRouter fallback models", len(fallbacks))
        return fallbacks
    except FileNotFoundError:
        LOGGER.warning("%s not found, no OpenRouter fallback models", path.name)
        return []
    except Exception as e:
        LOGGER.warning("Failed to load %s: %s", path.name, e)
        return []


def build_provider_chain(
    *,
    groq_api_key: str,
    groq_model: str,
    gemini_api_key: str,
    gemini_model: str,
    openrouter_api_key: str,
    openrouter_model: str,
    data_dir: Path,
    timeout: float,
    provider_order: tuple[str, ...] = ("groq", "gemini", "openrouter"),
) -> list[ProviderEntry]:
    """Build ordered provider entries to try in sequence.

    provider_order controls fallback priority, e.g.:
      ("groq", "gemini", "openrouter")  — speed-first (Twitch)
      ("gemini", "groq", "openrouter")  — quality-first (Discord)

    Providers with missing API keys are skipped silently.
    Raises ValueError if no providers are configured.
    """
    entries: dict[str, list[ProviderEntry]] = {}

    if groq_api_key.strip():
        model = groq_model.strip() or "llama-3.3-70b-versatile"
        entries["groq"] = [
            ProviderEntry(
                client=AsyncOpenAI(base_url=_GROQ_BASE_URL, api_key=groq_api_key, timeout=timeout),
                model=model,
            )
        ]
        LOGGER.info("AI provider: Groq (%s)", model)

    if gemini_api_key.strip():
        model = gemini_model.strip() or "gemini-1.5-flash"
        entries["gemini"] = [
            ProviderEntry(
                client=AsyncOpenAI(
                    base_url=_GEMINI_BASE_URL, api_key=gemini_api_key, timeout=timeout
                ),
                model=model,
            )
        ]
        LOGGER.info("AI provider: Gemini (%s)", model)

    if openrouter_api_key.strip():
        or_client = AsyncOpenAI(
            base_url=_OPENROUTER_BASE_URL, api_key=openrouter_api_key, timeout=timeout
        )
        or_extra: dict[str, Any] = {"extra_body": {"include_reasoning": False}}
        primary = openrouter_model.strip()
        or_entries: list[ProviderEntry] = []
        if primary:
            or_entries.append(ProviderEntry(client=or_client, model=primary, extra_kwargs=or_extra))
        fallbacks = _load_openrouter_fallbacks(data_dir, primary)
        for m in fallbacks:
            or_entries.append(ProviderEntry(client=or_client, model=m, extra_kwargs=or_extra))
        if or_entries:
            entries["openrouter"] = or_entries
        LOGGER.info(
            "AI provider: OpenRouter (primary=%s, fallbacks=%d)", primary or "none", len(fallbacks)
        )

    chain = [entry for name in provider_order for entry in entries.get(name, [])]

    if not chain:
        raise ValueError(
            "No AI providers configured. Set at least one of: "
            "GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY"
        )

    return chain


def get_primary_model_label(
    *,
    groq_api_key: str,
    groq_model: str,
    gemini_api_key: str,
    gemini_model: str,
    openrouter_api_key: str,
    openrouter_model: str,
    provider_order: tuple[str, ...],
) -> str | None:
    """Return the label of the first configured provider's model, e.g. 'groq/llama-3.3-70b-versatile'."""
    candidates: dict[str, tuple[str, str, str]] = {
        "groq": (groq_api_key, groq_model, "llama-3.3-70b-versatile"),
        "gemini": (gemini_api_key, gemini_model, "gemini-1.5-flash"),
        "openrouter": (openrouter_api_key, openrouter_model, "(free models)"),
    }
    for name in provider_order:
        api_key, model, default = candidates[name]
        if api_key.strip():
            return f"{name}/{model.strip() or default}"
    return None


async def call_provider_chain(
    chain: list[ProviderEntry],
    messages: list[ChatCompletionMessageParam],
    max_tokens: int,
) -> tuple[str, Exception | None]:
    """Try each provider in order, returning (cleaned_response, last_error).

    Returns ("", last_error) if all providers fail, ("text", None) on success.
    AuthenticationError and PermissionDeniedError are not caught here — they propagate
    to the caller so platform-specific error messages can be shown.
    """
    last_error: Exception | None = None
    t_start = time.monotonic()

    for entry in chain:
        try:
            completion = await entry.client.chat.completions.create(
                model=entry.model,
                max_tokens=max_tokens,
                messages=messages,
                **entry.extra_kwargs,
            )
            if not completion.choices:
                LOGGER.warning("AI [%s]: no choices, trying next", entry.model)
                continue
            raw = completion.choices[0].message.content or ""
            cleaned = strip_think_tags(raw)
            elapsed = time.monotonic() - t_start
            LOGGER.debug(
                "AI [%s]: %.1fs, raw=%d, clean=%d", entry.model, elapsed, len(raw), len(cleaned)
            )
            if cleaned:
                return cleaned, None
        except RateLimitError as e:
            LOGGER.warning("AI rate limit on %s, trying next", entry.model)
            last_error = e
        except APITimeoutError as e:
            LOGGER.warning("AI [%s] timed out, trying next", entry.model)
            last_error = e
        except NotFoundError as e:
            LOGGER.warning("AI [%s] not found (404), trying next", entry.model)
            last_error = e
        except Exception as e:
            LOGGER.warning("AI [%s] error (%s), trying next", entry.model, type(e).__name__)
            last_error = e

    return "", last_error
