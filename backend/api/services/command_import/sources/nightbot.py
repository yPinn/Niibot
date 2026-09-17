"""Nightbot import source.

Nightbot's unauthenticated read redacts every variable — ``$(user)`` comes back
as ``[user]`` and ``$(customapi …)`` as ``[customapi]``, with no way to recover
the original. Roughly a quarter of real commands are affected, so this source
goes through OAuth and reads the authenticated endpoints instead.

The token is never persisted: it is exchanged, used, and revoked inside the one
request that handles the OAuth callback.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..mapping import (
    check_length,
    classify,
    default_command_item,
    find_conflict,
    nightbot_role,
    normalize_command_name,
    translate_variables,
)
from ..models import ImportItem, ImportPreview, ImportSource
from ._http import get_json

LOGGER: logging.Logger = logging.getLogger(__name__)

API_BASE = "https://api.nightbot.tv/1"
OAUTH_AUTHORIZE = "https://api.nightbot.tv/oauth2/authorize"
OAUTH_TOKEN = "https://api.nightbot.tv/oauth2/token"
OAUTH_REVOKE = "https://api.nightbot.tv/oauth2/token/revoke"

# commands_default lets us read which Nightbot defaults the channel turned on,
# so the preview can offer the matching Niibot builtins. Same consent screen.
OAUTH_SCOPES = "commands commands_default"

_SOURCE = ImportSource.NIGHTBOT.value


class NightbotAuthError(Exception):
    """The OAuth exchange or an authenticated read failed."""


class NightbotSource:
    """Builds an ImportPreview from a channel's authenticated Nightbot data."""

    def __init__(self, http: httpx.AsyncClient, client_id: str, client_secret: str) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = httpx.QueryParams(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "scope": OAUTH_SCOPES,
                "state": state,
            }
        )
        return f"{OAUTH_AUTHORIZE}?{params}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        try:
            response = await self._http.post(
                OAUTH_TOKEN,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
        except httpx.HTTPError as exc:
            raise NightbotAuthError(f"token request failed: {exc}") from exc
        if response.status_code != 200:
            raise NightbotAuthError(f"token exchange returned {response.status_code}")
        token = response.json().get("access_token")
        if not token:
            raise NightbotAuthError("token response contained no access_token")
        return str(token)

    async def revoke(self, token: str) -> None:
        """Best effort — a token we failed to revoke still expires on its own."""
        try:
            await self._http.post(OAUTH_REVOKE, data={"token": token})
        except httpx.HTTPError as exc:
            LOGGER.warning("Nightbot token revoke failed: %s", exc)

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch_preview(self, token: str, existing: set[str]) -> ImportPreview:
        # All three reads depend only on the token, and this runs inside the
        # OAuth callback with the user's browser waiting on the redirect —
        # one round trip instead of three.
        me, custom_body, default_body = await asyncio.gather(
            self._get("/me", token),
            self._get("/commands", token),
            self._get("/commands/default", token),
        )
        login = str(((me or {}).get("user") or {}).get("displayName") or "")
        custom = (custom_body or {}).get("commands") or []
        defaults = (default_body or {}).get("commands") or []

        items: list[ImportItem] = [
            item for raw in defaults if (item := self._map_default(raw)) is not None
        ]
        # Nightbot's alias points at another command; resolve it into a redirect
        # so the imported command keeps calling its target.
        items += [self._map_custom(raw, existing) for raw in custom]

        return ImportPreview(
            source=ImportSource.NIGHTBOT,
            source_channel=login,
            items=items,
        )

    async def _get(self, path: str, token: str):
        return await get_json(
            self._http,
            f"{API_BASE}{path}",
            label="Nightbot",
            headers={"Authorization": f"Bearer {token}"},
        )

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_default(raw: dict) -> ImportItem | None:
        if not raw.get("enabled", True):
            return None
        command = normalize_command_name(str(raw.get("name") or ""))
        if not command:
            return None
        return default_command_item(command, key_prefix="nb", platform="Nightbot")

    @staticmethod
    def _map_custom(raw: dict, existing: set[str]) -> ImportItem:
        source_name = str(raw.get("name") or "")
        name = normalize_command_name(source_name)
        message = str(raw.get("message") or "")
        alias = normalize_command_name(str(raw.get("alias") or ""))

        notes: list[str] = []
        blockers: list[str] = []

        if alias:
            # Nightbot alias semantics: run `alias`, passing `message` as its
            # arguments. Our "!target …" redirect is the same thing.
            response = f"!{alias} {message}".strip()
            original = f"→ !{alias} {message}".strip()
            notes.append(f"Nightbot 的別名設定，改為轉呼叫 !{alias}")
        else:
            response, translate_notes, blockers = translate_variables(message, _SOURCE)
            original = message
            notes += translate_notes

        role, role_notes = nightbot_role(raw.get("userLevel"))
        notes = [*role_notes, *notes]

        if _looks_redacted(message):
            blockers.append(
                "Nightbot 沒有回傳這則指令的變數內容，無法還原（請確認授權包含 commands 權限）"
            )

        if not name:
            blockers.append("指令名稱無法轉換")
        blockers += check_length(response)

        status, section, notes = classify(notes, blockers, find_conflict(name, existing))

        cooldown = int(raw.get("coolDown") or 0)
        return ImportItem(
            key=f"nb:cmd:{name or source_name}",
            section=section,
            status=status,
            source_name=source_name if source_name.startswith("!") else f"!{source_name}",
            source_enabled=True,
            notes=notes,
            command_name=name or None,
            response=response,
            original_response=original,
            cooldown=cooldown or None,
            min_role=role,
        )


# Nightbot's public read replaces "$(user)" with "[user]". If we see those
# markers on an authenticated read something is wrong with the token, and
# importing the text as-is would save a broken command.
_REDACTION_MARKERS = (
    "[user]",
    "[touser]",
    "[query]",
    "[count]",
    "[channel]",
    "[eval",
    "[urlfetch",
    "[customapi",
)


def _looks_redacted(message: str) -> bool:
    return any(marker in message for marker in _REDACTION_MARKERS)
