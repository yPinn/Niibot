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
    BUILTIN_AUDIENCES,
    BUILTIN_CATEGORIES,
    BUILTIN_DEFS,
    BUILTIN_DESCRIPTIONS,
    BUILTIN_DETAILS,
    BUILTIN_PREVIEWS,
    BUILTIN_USAGE,
    PUBLIC_DESCRIPTIONS,
)

# Mirrors twitch.core.guards.ROLE_HIERARCHY (kept local to avoid importing the
# twitch package — and twitchio — into a shared-layer test).
_VALID_ROLES = {"everyone", "subscriber", "vip", "moderator", "broadcaster"}


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


def test_every_viewer_builtin_has_a_public_description() -> None:
    viewer_names = {name for name, audience in BUILTIN_AUDIENCES.items() if audience == "viewer"}
    assert set(PUBLIC_DESCRIPTIONS) == viewer_names


def test_declared_min_roles_are_valid() -> None:
    for defn in BUILTIN_DEFS:
        role = defn.get("min_role", "everyone")
        assert role in _VALID_ROLES, f"{defn['command_name']}: bad min_role {role!r}"


def test_every_builtin_has_audience_usage_and_detail() -> None:
    names = {d["command_name"] for d in BUILTIN_DEFS}
    assert set(BUILTIN_AUDIENCES) == names
    assert set(BUILTIN_USAGE) == names
    assert set(BUILTIN_DETAILS) == names
    assert set(BUILTIN_PREVIEWS) == names
    assert set(BUILTIN_AUDIENCES.values()) <= {"viewer", "broadcaster", "moderator"}


def test_builtin_previews_are_safe_static_examples() -> None:
    for name, preview in BUILTIN_PREVIEWS.items():
        assert preview["input"].startswith("!")
        assert preview["output"].strip(), f"{name}: missing preview output"


def test_catalog_orders_frequent_viewer_tasks_before_privileged_tools() -> None:
    category_runs = [cat for cat, _ in groupby(d["category"] for d in BUILTIN_DEFS)]
    assert category_runs == ["common", "viewer", "fun", "game", "broadcaster", "moderator"]


def test_subcount_is_a_broadcaster_tool() -> None:
    by_name = {d["command_name"]: d for d in BUILTIN_DEFS}
    assert BUILTIN_AUDIENCES["subcount"] == "broadcaster"
    assert by_name["subcount"]["category"] == "broadcaster"
    assert by_name["subcount"]["min_role"] == "broadcaster"


def test_moderator_only_builtins_declare_min_role() -> None:
    """!so and !condemn act as the streamer/mods and must not default to everyone
    — the handlers no longer gate on their own."""
    by_name = {d["command_name"]: d for d in BUILTIN_DEFS}
    for name in ("so", "condemn"):
        assert by_name[name].get("min_role") == "moderator", (
            f"!{name} must declare min_role='moderator'"
        )
