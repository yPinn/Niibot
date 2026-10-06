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
    BUILTIN_INTEGRATIONS,
    BUILTIN_PREVIEWS,
    BUILTIN_USAGE,
    COMMAND_RESERVED_NAMES,
    PUBLIC_DESCRIPTIONS,
    RUNTIME_ONLY_COMMAND_NAMES,
)

# Mirrors twitch.core.guards.ROLE_HIERARCHY (kept local to avoid importing the
# twitch package — and twitchio — into a shared-layer test).
_VALID_ROLES = {"everyone", "subscriber", "vip", "moderator", "broadcaster"}

_EXPECTED_CATALOG = [
    ("help", "common", True, ("指令",)),
    ("checkin", "common", True, ("簽到",)),
    ("schedule", "common", True, ("下次開台", "排程")),
    ("uptime", "common", False, ("開播時間",)),
    ("ping", "common", True, ("alive",)),
    ("del", "common", False, ("刪", "vanish")),
    ("rank", "viewer", True, ("排名",)),
    ("np", "viewer", True, ("影片",)),
    ("followage", "viewer", False, ("追隨時間",)),
    ("subage", "viewer", False, ("訂閱資訊",)),
    ("accountage", "viewer", False, ("帳號年齡",)),
    ("bits", "viewer", False, ("小奇點",)),
    ("quote", "viewer", False, ("語錄",)),
    ("choose", "fun", True, ("選",)),
    ("fortune", "fun", True, ("運勢",)),
    ("tarot", "fun", True, ("塔羅",)),
    ("roll", "fun", False, ("輪盤",)),
    ("crosshairs", "game", False, ("xhc", "準星")),
    ("tft", "game", False, ("戰棋",)),
    ("title", "channel", False, ("標題",)),
    ("game", "channel", False, ("分類",)),
    ("tags", "channel", False, ("標籤",)),
    ("subcount", "broadcaster", False, ("訂閱數",)),
    ("so", "moderator", False, ("推薦",)),
    ("marker", "moderator", False, ("標記",)),
    ("winner", "moderator", False, ("抽",)),
    ("condemn", "moderator", False, ("斥責",)),
]

_EXPECTED_DESCRIPTIONS = {
    "help": "查看可用的公開指令",
    "checkin": "每日簽到並查看累積天數",
    "schedule": "查看今天或下次的開台排程",
    "uptime": "查看目前已開播多久",
    "ping": "確認 Niibot 是否在線",
    "del": "清除自己最近的聊天室留言",
    "rank": "查看累積簽到排名",
    "np": "查看正在播放的點播影片",
    "followage": "查看自己追隨頻道多久",
    "subage": "查看累積訂閱月數與目前方案",
    "accountage": "查看 Twitch 帳號建立時間",
    "bits": "查看小奇點排名與累積總額",
    "quote": "查看頻道語錄",
    "choose": "從多個選項中隨機挑選一個",
    "fortune": "查看今日運勢",
    "tarot": "查看每日塔羅",
    "roll": "觸發者有機率 timeout 60 秒",
    "crosshairs": "查看頻道準星收藏",
    "tft": "查看聯盟戰棋排名",
    "title": "查看或修改頻道標題",
    "game": "查看或修改頻道分類",
    "tags": "查看或修改頻道標籤",
    "subcount": "查看頻道訂閱總數",
    "so": "推薦指定頻道",
    "marker": "標記目前直播時間點",
    "winner": "隨機抽出一位在線觀眾",
    "condemn": "發送頻道反惡意言論聲明",
}

_EXPECTED_PUBLIC_DESCRIPTIONS = {
    "help": "查看可用的公開指令",
    "checkin": "每日簽到並查看累積天數",
    "schedule": "查看今天或下次的開台排程",
    "uptime": "查看目前已開播多久",
    "ping": "確認 Niibot 是否在線",
    "del": "清除自己最近的聊天室留言",
    "rank": "查看累積簽到排名",
    "np": "查看正在播放的點播影片",
    "followage": "查看自己追隨頻道多久",
    "subage": "查看累積訂閱月數與目前方案",
    "accountage": "查看 Twitch 帳號建立時間；用法：!accountage [使用者]",
    "bits": "查看小奇點排名與累積總額",
    "quote": "查看頻道語錄；Mod 以上可新增或刪除",
    "choose": "從多個選項中隨機挑選一個；用法：!choose <選項1> <選項2> …",
    "fortune": "查看今日運勢",
    "tarot": "查看每日塔羅；用法：!tarot [綜合／感情／事業／財運]",
    "roll": "觸發者有機率 timeout 60 秒",
    "crosshairs": "查看頻道準星收藏",
    "tft": "查看聯盟戰棋排名；用法：!tft <玩家名稱>#<Tag>",
    "title": "查看頻道標題；Mod 以上可帶參數修改",
    "game": "查看頻道分類；Mod 以上可帶參數修改",
    "tags": "查看頻道標籤；Mod 以上可帶參數修改",
}


def _aliases(defn: dict) -> tuple[str, ...]:
    return tuple(alias.strip() for alias in (defn.get("aliases") or "").split(",") if alias.strip())


def test_catalog_defaults_are_an_explicit_reviewed_snapshot() -> None:
    actual = [
        (
            defn["command_name"],
            defn["category"],
            defn.get("enabled", True),
            _aliases(defn),
        )
        for defn in BUILTIN_DEFS
    ]

    assert actual == _EXPECTED_CATALOG


def test_concise_chinese_aliases_are_unambiguous_and_minimal() -> None:
    expected = {
        "title": ("標題",),
        "winner": ("抽",),
        "choose": ("選",),
        "del": ("刪", "vanish"),
    }
    by_name = {defn["command_name"]: _aliases(defn) for defn in BUILTIN_DEFS}

    assert {name: by_name[name] for name in expected} == expected
    assert {"標", "推", "輪"}.isdisjoint(COMMAND_RESERVED_NAMES)


def test_builtin_descriptions_use_one_concise_style() -> None:
    assert BUILTIN_DESCRIPTIONS == _EXPECTED_DESCRIPTIONS
    assert all("Mod 指令" not in description for description in BUILTIN_DESCRIPTIONS.values())
    assert all(len(description) <= 25 for description in BUILTIN_DESCRIPTIONS.values())


def test_public_descriptions_match_the_same_voice_and_keep_only_needed_help() -> None:
    assert PUBLIC_DESCRIPTIONS == _EXPECTED_PUBLIC_DESCRIPTIONS
    assert all("查詢" not in description for description in PUBLIC_DESCRIPTIONS.values())


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

    assert BUILTIN_PREVIEWS["roll"] == {
        "input": "!roll",
        "output": "@小霓 被狼人選中，timeout 60 秒！",
    }
    assert BUILTIN_DETAILS["roll"] == ("觸發者有機率被 timeout 60 秒；Niibot 需為 Mod。")


def test_catalog_orders_frequent_viewer_tasks_before_privileged_tools() -> None:
    category_runs = [cat for cat, _ in groupby(d["category"] for d in BUILTIN_DEFS)]
    assert category_runs == [
        "common",
        "viewer",
        "fun",
        "game",
        "channel",
        "broadcaster",
        "moderator",
    ]


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


def test_crosshairs_catalog_owns_its_runtime_short_alias() -> None:
    by_name = {d["command_name"]: d for d in BUILTIN_DEFS}
    aliases = {alias.strip() for alias in by_name["crosshairs"]["aliases"].split(",")}

    assert aliases == {"xhc", "準星"}


def test_runtime_only_commands_are_reserved_from_custom_commands() -> None:
    assert RUNTIME_ONLY_COMMAND_NAMES == {
        "ai",
        "問",
        "ovltest",
        "cmd",
        "gq",
        "comp",
        "vq",
    }
    assert RUNTIME_ONLY_COMMAND_NAMES <= COMMAND_RESERVED_NAMES
    # np moved into the catalog; its names must stay reserved through it.
    assert {"np", "影片"} <= COMMAND_RESERVED_NAMES


def test_external_default_compatibility_name_is_reserved() -> None:
    # Nightbot/StreamElements !commands converts to Niibot !help.  Letting a
    # custom command claim the source name would make the import ambiguous.
    assert "commands" in COMMAND_RESERVED_NAMES


def test_builtin_names_and_aliases_share_one_collision_free_namespace() -> None:
    owners: dict[str, str] = {}
    for defn in BUILTIN_DEFS:
        name = defn["command_name"].strip().lower()
        assert name not in owners, f"duplicate builtin name: {name}"
        owners[name] = name
        for alias in (defn.get("aliases") or "").split(","):
            alias = alias.strip().lower()
            if not alias:
                continue
            assert alias != name, f"{name}: alias repeats its canonical name"
            assert alias not in owners, f"{alias!r} belongs to both {owners[alias]} and {name}"
            owners[alias] = name

    assert set(owners) <= COMMAND_RESERVED_NAMES


def test_every_builtin_declares_its_external_integration_contract() -> None:
    names = {d["command_name"] for d in BUILTIN_DEFS}
    assert set(BUILTIN_INTEGRATIONS) == names

    for name, integration in BUILTIN_INTEGRATIONS.items():
        assert integration["kind"] in {
            "internal",
            "twitch_public",
            "twitch_capability",
            "external_service",
        }
        assert integration["label"], f"{name}: missing integration label"
        assert isinstance(integration["conditions"], list)
        for requirement in integration["requirements"]:
            assert requirement["mode"] in {"all", "write", "effect"}
            assert isinstance(requirement["requires_bot_moderator"], bool)


def test_privileged_twitch_commands_declare_exact_capability_subjects() -> None:
    expected = {
        "del": ("banned_users", "all", True),
        "followage": ("followers", "all", True),
        "subage": ("subscriptions", "all", False),
        "bits": ("cheers", "all", False),
        "roll": ("banned_users", "effect", True),
        "subcount": ("subscriptions", "all", False),
        "title": ("channel_info", "write", False),
        "game": ("channel_info", "write", False),
        "tags": ("channel_info", "write", False),
        "so": ("shoutouts", "all", True),
        "marker": ("channel_info", "all", False),
        "winner": ("chatters", "all", True),
    }

    actual = {
        name: (
            integration["requirements"][0]["capability_key"],
            integration["requirements"][0]["mode"],
            integration["requirements"][0]["requires_bot_moderator"],
        )
        for name, integration in BUILTIN_INTEGRATIONS.items()
        if integration["requirements"]
    }
    assert actual == expected
