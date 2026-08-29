"""Consistency tests for the builtin command catalog (shared.builtin_commands).

Like test_event_catalog.py, the point is that adding a builtin in one place but
forgetting the matching entry elsewhere fails loudly here instead of shipping a
command with no description or an orphan category. The dashboard renders a group
header each time ``category`` changes down BUILTIN_DEFS, so it also checks that
every category's rows stay contiguous.
"""

from __future__ import annotations

from itertools import groupby

from shared.builtin_commands import (
    BUILTIN_CATEGORIES,
    BUILTIN_DEFS,
    BUILTIN_DESCRIPTIONS,
    PUBLIC_DESCRIPTIONS,
)


def test_every_def_has_a_known_category() -> None:
    for defn in BUILTIN_DEFS:
        assert "category" in defn, f"{defn['command_name']}: missing 'category'"
        assert defn["category"] in BUILTIN_CATEGORIES, (
            f"{defn['command_name']}: unknown category {defn['category']!r}"
        )


def test_categories_are_contiguous() -> None:
    """Each category must appear as one unbroken run — the dashboard groups by
    order, it does not bucket."""
    seen: list[str] = [cat for cat, _ in groupby(d["category"] for d in BUILTIN_DEFS)]
    assert len(seen) == len(set(seen)), f"a category is split across BUILTIN_DEFS: {seen}"


def test_no_orphan_categories() -> None:
    used = {d["category"] for d in BUILTIN_DEFS}
    orphans = set(BUILTIN_CATEGORIES) - used
    assert not orphans, f"BUILTIN_CATEGORIES keys with no command: {orphans}"


def test_every_builtin_has_a_description() -> None:
    missing = [
        d["command_name"] for d in BUILTIN_DEFS if d["command_name"] not in BUILTIN_DESCRIPTIONS
    ]
    assert not missing, f"builtins missing from BUILTIN_DESCRIPTIONS: {missing}"


def test_public_descriptions_are_a_subset_of_builtins() -> None:
    names = {d["command_name"] for d in BUILTIN_DEFS}
    extra = set(PUBLIC_DESCRIPTIONS) - names
    assert not extra, f"PUBLIC_DESCRIPTIONS names not in BUILTIN_DEFS: {extra}"
