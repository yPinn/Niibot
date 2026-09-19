"""Small deterministic alias matcher for bounded Role-play lore."""

from __future__ import annotations

from dataclasses import dataclass

from shared.roleplay.contracts import LoreEntry, ResolvedLore, RoleplayPackage, SpoilerPolicy
from shared.roleplay.normalization import normalize_roleplay_text


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: LoreEntry
    strength: int
    matched_chars: int
    source_index: int


def _match(entry: LoreEntry, normalized_query: str, source_index: int) -> _Candidate | None:
    best_strength = 0
    best_chars = 0
    for raw_term in (entry.subject, *entry.aliases):
        term = normalize_roleplay_text(raw_term)
        if not term:
            continue
        if normalized_query == term:
            strength = 2
        elif term in normalized_query:
            strength = 1
        else:
            continue
        if (strength, len(term)) > (best_strength, best_chars):
            best_strength = strength
            best_chars = len(term)
    if best_strength == 0:
        return None
    return _Candidate(entry, best_strength, best_chars, source_index)


def resolve_lore(
    package: RoleplayPackage,
    query: str,
    *,
    max_entries: int = 2,
    max_chars: int = 1_500,
) -> ResolvedLore:
    """Resolve complete eligible entries; never truncate factual lore content."""

    if max_entries <= 0 or max_chars <= 0:
        raise ValueError("lore retrieval budgets must be positive")
    normalized_query = normalize_roleplay_text(query)
    if not normalized_query:
        return ResolvedLore(entries=(), total_chars=0)

    candidates: list[_Candidate] = []
    for index, entry in enumerate(package.lore_entries):
        if not entry.known_at_stage:
            continue
        if entry.contains_spoilers and package.world.spoiler_policy is SpoilerPolicy.FORBID:
            continue
        candidate = _match(entry, normalized_query, index)
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate.strength,
            -candidate.entry.priority,
            -candidate.matched_chars,
            normalize_roleplay_text(candidate.entry.subject),
            candidate.source_index,
        )
    )

    selected: list[LoreEntry] = []
    total_chars = 0
    for candidate in candidates:
        content_chars = len(candidate.entry.content)
        if total_chars + content_chars > max_chars:
            continue
        selected.append(candidate.entry)
        total_chars += content_chars
        if len(selected) >= max_entries:
            break
    return ResolvedLore(entries=tuple(selected), total_chars=total_chars)
