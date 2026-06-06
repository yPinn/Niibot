"""Knowledge pack loader and entry matcher for AI harness injection.

Packs are Markdown files in data/knowledge_packs/*.md with YAML-like frontmatter
and ## Section entries. Only entries whose keys match the user query are injected
into the system prompt — the rest remain invisible to the LLM.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# Rough token budget guard: total content chars / 4 > limit → reject pack at load time.
_MAX_PACK_TOKENS = 6000


@dataclass
class PackEntry:
    keys: list[str]  # all lowercase; used for keyword matching against query
    content: str


@dataclass
class KnowledgePack:
    id: str
    name: str
    description: str
    entries: list[PackEntry] = field(default_factory=list)


# ── Parsing ──────────────────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML-like frontmatter from body. Returns (meta_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    front, body = parts[1], parts[2]
    meta: dict[str, str] = {}
    for line in front.strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body.strip()


def _parse_entries(body: str) -> list[PackEntry]:
    """Parse ## sections into PackEntry objects.

    Each section must have a 'keys: ...' line immediately after the heading.
    Sections without keys are silently skipped (allows intro text at top of file).
    """
    entries: list[PackEntry] = []
    # Prepend newline so the first "## " is split consistently with the rest.
    sections = ("\n" + body).split("\n## ")[1:]
    for section in sections:
        lines = section.strip().splitlines()
        if len(lines) < 2:
            continue
        # lines[0] is the heading text; look for 'keys:' in the next lines.
        body_lines = lines[1:]
        keys: list[str] = []
        content_start = 0
        for i, line in enumerate(body_lines):
            stripped = line.strip()
            if stripped.lower().startswith("keys:"):
                raw = stripped[5:].strip()
                keys = [k.strip().lower() for k in raw.split(",") if k.strip()]
                content_start = i + 1
                break
        if not keys:
            continue
        content = "\n".join(body_lines[content_start:]).strip()
        if content:
            entries.append(PackEntry(keys=keys, content=content))
    return entries


# ── Loader ───────────────────────────────────────────────────────────────────


def _load_pack(path: Path) -> KnowledgePack | None:
    try:
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        pack_id = meta.get("id") or path.stem
        name = meta.get("name") or pack_id
        description = meta.get("description") or ""
        entries = _parse_entries(body)
        total_chars = sum(len(e.content) for e in entries)
        if total_chars // 4 > _MAX_PACK_TOKENS:
            LOGGER.warning(
                "Pack %s exceeds token limit (%d estimated tokens), skipping",
                pack_id,
                total_chars // 4,
            )
            return None
        pack = KnowledgePack(id=pack_id, name=name, description=description, entries=entries)
        LOGGER.info("Loaded pack '%s': %d entries", pack_id, len(entries))
        return pack
    except Exception:
        LOGGER.warning("Failed to load pack %s", path.name, exc_info=True)
        return None


def load_packs(data_dir: Path) -> dict[str, KnowledgePack]:
    """Load all *.md packs from data_dir/knowledge_packs/. Returns {id: pack}."""
    packs_dir = data_dir / "knowledge_packs"
    if not packs_dir.exists():
        LOGGER.debug("No knowledge_packs directory found at %s", packs_dir)
        return {}
    result: dict[str, KnowledgePack] = {}
    for path in sorted(packs_dir.glob("*.md")):
        pack = _load_pack(path)
        if pack:
            result[pack.id] = pack
    LOGGER.info("Knowledge packs loaded: %d total", len(result))
    return result


# ── Matcher ──────────────────────────────────────────────────────────────────


def match_entries(
    packs: dict[str, KnowledgePack],
    enabled_ids: list[str],
    query: str,
) -> list[tuple[str, str]]:
    """Return (pack_name, entry_content) pairs for entries whose keys appear in query.

    Matching uses word-boundary anchors (\b) so that short keys like "w" or "l"
    do not false-positive inside longer tokens like "kekw" or "lul".

    Only packs listed in enabled_ids are searched. Order follows enabled_ids order
    so streamer-configured priority is preserved.
    """
    query_lower = query.lower()
    results: list[tuple[str, str]] = []
    for pack_id in enabled_ids:
        pack = packs.get(pack_id)
        if not pack:
            continue
        for entry in pack.entries:
            if any(re.search(r"\b" + re.escape(key) + r"\b", query_lower) for key in entry.keys):
                results.append((pack.name, entry.content))
    return results
