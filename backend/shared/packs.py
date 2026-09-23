"""Pack loader and entry matcher for AI harness injection.

Pack structure mirrors Claude Skills (one directory per pack with an index file):

    data/packs/
    ├── <pack_id>/
    │   ├── PACK.md             # frontmatter only: id, name, description
    │   ├── <entry>.md          # frontmatter (keys) + body
    │   └── <topic>/<sub>.md    # optional nested subdirs for grouping

Each entry .md is matched independently against the user query by its `keys:`
frontmatter; only matched entries are injected into the system prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# Rough token budget guard: total content chars / 4 > limit → reject pack at load time.
_MAX_PACK_TOKENS = 6000

_PACKS_DIRNAME = "packs"
_PACK_INDEX = "PACK.md"

# Keys consisting entirely of ASCII chars use word-boundary regex so short
# tokens (e.g. "w") don't match inside longer words ("kekw"). Keys containing
# any non-ASCII char (e.g. CJK) use plain substring matching, since `\b`
# requires an ASCII-word ↔ non-word transition that CJK text never produces.
_ASCII_KEY = re.compile(r"^[\x00-\x7f]+$")


@dataclass
class PackEntry:
    keys: list[str]  # all lowercase; used for keyword matching against query
    content: str
    path: tuple[str, ...]  # relative path parts (no extension) e.g. ("kappa",) or ("topic", "sub")


@dataclass
class Pack:
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


def _load_entry(md_path: Path, pack_dir: Path) -> PackEntry | None:
    """Parse one entry .md file. Returns None when the file has no `keys:` frontmatter."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        LOGGER.warning("Failed to read entry %s", md_path, exc_info=True)
        return None
    meta, body = _parse_frontmatter(text)
    keys_raw = meta.get("keys", "")
    keys = [k.strip().lower() for k in keys_raw.split(",") if k.strip()]
    if not keys or not body:
        return None
    rel = md_path.relative_to(pack_dir).with_suffix("")
    return PackEntry(keys=keys, content=body, path=tuple(rel.parts))


# ── Loader ───────────────────────────────────────────────────────────────────


def _load_pack(pack_dir: Path) -> Pack | None:
    pack_md = pack_dir / _PACK_INDEX
    if not pack_md.exists():
        LOGGER.warning("Pack directory %s missing %s, skipping", pack_dir.name, _PACK_INDEX)
        return None
    try:
        meta, _ = _parse_frontmatter(pack_md.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("Failed to read %s/%s", pack_dir.name, _PACK_INDEX, exc_info=True)
        return None
    pack_id = meta.get("id") or pack_dir.name
    name = meta.get("name") or pack_id
    description = meta.get("description") or ""

    entries: list[PackEntry] = []
    for md_path in sorted(pack_dir.rglob("*.md")):
        if md_path.name == _PACK_INDEX:
            continue
        entry = _load_entry(md_path, pack_dir)
        if entry:
            entries.append(entry)

    total_chars = sum(len(e.content) for e in entries)
    if total_chars // 4 > _MAX_PACK_TOKENS:
        LOGGER.warning(
            "Pack %s exceeds token limit (%d estimated tokens), skipping",
            pack_id,
            total_chars // 4,
        )
        return None
    LOGGER.info("Loaded pack '%s': %d entries", pack_id, len(entries))
    return Pack(id=pack_id, name=name, description=description, entries=entries)


def load_packs(data_dir: Path) -> dict[str, Pack]:
    """Load all packs from data_dir/packs/<pack>/. Returns {id: pack}."""
    packs_dir = data_dir / _PACKS_DIRNAME
    if not packs_dir.exists():
        LOGGER.debug("No %s directory found at %s", _PACKS_DIRNAME, packs_dir)
        return {}
    result: dict[str, Pack] = {}
    for entry in sorted(packs_dir.iterdir()):
        if not entry.is_dir():
            continue
        pack = _load_pack(entry)
        if pack:
            result[pack.id] = pack
    LOGGER.info("Packs loaded: %d total", len(result))
    return result


# ── Matcher ──────────────────────────────────────────────────────────────────


def match_entries(
    packs: dict[str, Pack],
    enabled_ids: list[str],
    query: str,
) -> list[tuple[str, str]]:
    """Return (display_label, entry_content) pairs whose keys appear in the query.

    `display_label` is `<pack.name> / <path>/<parts>` so the LLM sees the topical
    breadcrumb. ASCII-only keys use word-boundary regex (avoiding false hits like
    "w" inside "kekw"); keys containing CJK use plain substring matching since
    `\\b` requires an ASCII word transition.

    Only packs listed in enabled_ids are searched. Order follows enabled_ids so
    streamer-configured priority is preserved.
    """
    query_lower = query.lower()
    results: list[tuple[str, str]] = []
    for pack_id in enabled_ids:
        pack = packs.get(pack_id)
        if not pack:
            continue
        for entry in pack.entries:
            if any(_key_matches(key, query_lower) for key in entry.keys):
                label = pack.name + " / " + " / ".join(entry.path)
                results.append((label, entry.content))
    return results


def _key_matches(key: str, query: str) -> bool:
    if _ASCII_KEY.match(key):
        return (
            re.search(
                r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])",
                query,
            )
            is not None
        )
    return key in query
