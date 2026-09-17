"""Unit tests for command import translation.

The payload shapes here are trimmed from real Nightbot and StreamElements API
responses, so the assertions describe what these platforms actually send rather
than what their docs imply.
"""

from __future__ import annotations

import pytest

from services.command_import.mapping import (
    builtin_equivalent,
    find_conflict,
    nightbot_role,
    normalize_command_name,
    streamelements_role,
    translate_variables,
)
from services.command_import.models import ImportSection, ImportStatus
from services.command_import.sources.nightbot import NightbotSource
from services.command_import.sources.streamelements import StreamElementsSource

SE = "streamelements"
NB = "nightbot"


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class TestRoleMapping:
    @pytest.mark.parametrize(
        "user_level,expected",
        [
            ("everyone", "everyone"),
            ("subscriber", "subscriber"),
            ("twitch_vip", "vip"),
            ("moderator", "moderator"),
            ("owner", "broadcaster"),
        ],
    )
    def test_nightbot_levels(self, user_level: str, expected: str):
        assert nightbot_role(user_level)[0] == expected

    def test_nightbot_regular_tightens_to_subscriber(self):
        role, notes = nightbot_role("regular")
        assert role == "subscriber"
        assert notes, "the user should be told the level was changed"

    def test_nightbot_missing_level_defaults_to_everyone(self):
        assert nightbot_role(None)[0] == "everyone"

    def test_unknown_nightbot_level_locks_down(self):
        role, notes = nightbot_role("some_new_tier")
        assert role == "broadcaster"
        assert notes

    @pytest.mark.parametrize(
        "level,expected",
        [
            (100, "everyone"),
            (250, "subscriber"),
            (400, "vip"),
            (500, "moderator"),
            (1500, "broadcaster"),
        ],
    )
    def test_streamelements_levels(self, level: int, expected: str):
        assert streamelements_role(level)[0] == expected

    def test_streamelements_regular_tightens_to_subscriber(self):
        role, notes = streamelements_role(300)
        assert role == "subscriber"
        assert notes

    def test_streamelements_super_moderator_tightens_to_broadcaster(self):
        role, notes = streamelements_role(1000)
        assert role == "broadcaster"
        assert notes

    def test_unknown_high_level_locks_down(self):
        assert streamelements_role(9001)[0] == "broadcaster"


# ---------------------------------------------------------------------------
# Names and conflicts
# ---------------------------------------------------------------------------


class TestNames:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("!discord", "discord"),
            ("Discord", "discord"),
            ("  !SoCials ", "socials"),
            ("指令", "指令"),
            ("!pc-specs", "pc-specs"),
        ],
    )
    def test_normalize(self, raw: str, expected: str):
        assert normalize_command_name(raw) == expected

    def test_existing_command_is_a_conflict(self):
        assert find_conflict("discord", {"discord"}) == "discord"

    def test_builtin_name_is_a_conflict(self):
        assert find_conflict("uptime", set()) == "uptime"

    def test_builtin_alias_resolves_to_its_command(self):
        assert find_conflict("指令", set()) == "help"

    def test_name_we_have_no_builtin_for_is_not_a_conflict(self):
        # We do not ship !game, so importing one is perfectly fine. The import
        # never required us to reimplement the other platform's commands.
        assert find_conflict("game", set()) is None
        assert find_conflict("songrequest", set()) is None


class TestBuiltinEquivalents:
    def test_known_equivalents(self):
        assert builtin_equivalent("followage") == "followage"
        assert builtin_equivalent("!commands") == "help"

    def test_platform_features_have_no_equivalent(self):
        for command in ("points", "songrequest", "duel", "openstore", "kappagen"):
            assert builtin_equivalent(command) is None


# ---------------------------------------------------------------------------
# Variable translation
# ---------------------------------------------------------------------------


class TestStreamElementsVariables:
    @pytest.mark.parametrize(
        "source,expected",
        [
            ("${user} 你好", "$(user) 你好"),
            ("$(user) 你好", "$(user) 你好"),
            ("${sender} hi", "$(user) hi"),
            ("${sender.name} hi", "$(user) hi"),
            ("${user.name} hi", "$(user) hi"),
            ("${touser} hi", "$(touser) hi"),
            ("$(touser ) hi", "$(touser) hi"),
            ("${channel} 開台了", "$(channel) 開台了"),
            ("${count}", "$(count)"),
            ("${1} vs ${2}", "$(1) vs $(2)"),
            ("$(1:)", "$(1)"),
            ("${random.pick a,b,c}", "$(pick a,b,c)"),
            ("${random.1-100}", "$(random 1,100)"),
        ],
    )
    def test_translations(self, source: str, expected: str):
        translated, _, blockers = translate_variables(source, SE)
        assert translated == expected
        assert blockers == []

    def test_first_argument_with_sender_fallback_is_exactly_touser(self):
        # "$(1|$(sender))" is the single most common StreamElements idiom and
        # means precisely what our $(touser) means.
        translated, _, blockers = translate_variables("@$(1|$(sender)) ->", SE)
        assert translated == "@$(touser) ->"
        assert blockers == []

    def test_dropped_default_is_reported(self):
        translated, notes, blockers = translate_variables("$(2|nobody)", SE)
        assert translated == "$(2)"
        assert blockers == []
        assert any("預設值" in n for n in notes)

    def test_empty_default_is_not_reported(self):
        _, notes, _ = translate_variables("$(1:)", SE)
        assert not any("預設值" in n for n in notes)

    @pytest.mark.parametrize(
        "source",
        [
            "$(customapi https://example.com)",
            "$(urlfetch https://example.com)",
            "${count deaths}",
            "${getcount deadwig}",
            "${setgame Valorant}",
            "${uptime}",
            "${user.lastseen}",
            "${channel.subs}",
            "${time.until 2026-01-01}",
            "${math 1+1}",
        ],
    )
    def test_unsupported_variables_are_blocked_with_a_reason(self, source: str):
        _, _, blockers = translate_variables(source, SE)
        assert blockers, f"{source} should be reported as unsupported"
        assert all(b.strip() for b in blockers)

    def test_named_counter_reason_mentions_count(self):
        _, _, blockers = translate_variables("${count deaths}", SE)
        assert any("$(count)" in b for b in blockers)

    def test_plain_text_is_untouched(self):
        text = "加入我們的 Discord https://discord.gg/example"
        translated, notes, blockers = translate_variables(text, SE)
        assert translated == text
        assert notes == []
        assert blockers == []


class TestNightbotVariables:
    def test_native_syntax_passes_through(self):
        text = "$(user) 擲出了 $(random 1,100) 點"
        translated, _, blockers = translate_variables(text, NB)
        assert translated == text
        assert blockers == []

    @pytest.mark.parametrize("source", ["$(querystring)", "$(arguments)"])
    def test_query_spellings_normalise(self, source: str):
        translated, _, blockers = translate_variables(source, NB)
        assert translated == "$(query)"
        assert blockers == []

    @pytest.mark.parametrize(
        "source",
        [
            "$(eval 1+1)",
            "$(urlfetch https://example.com)",
            "$(customapi https://example.com)",
            "$(twitch $(touser))",
            "$(weather Taipei)",
            "$(countdown 2026-01-01)",
        ],
    )
    def test_script_variables_are_blocked(self, source: str):
        _, _, blockers = translate_variables(source, NB)
        assert blockers


# ---------------------------------------------------------------------------
# StreamElements payload mapping
# ---------------------------------------------------------------------------


def se_command(**overrides) -> dict:
    """A custom command in the exact shape the StreamElements API returns."""
    base = {
        "command": "discord",
        "reply": "加入我們 https://discord.gg/example",
        "aliases": [],
        "keywords": [],
        "enabled": True,
        "hidden": False,
        "cost": 0,
        "type": "say",
        "accessLevel": 100,
        "cooldown": {"user": 15, "global": 5},
    }
    return {**base, **overrides}


class TestStreamElementsMapping:
    def test_plain_command(self):
        (item,) = StreamElementsSource._map_custom(se_command(), set())
        assert item.section is ImportSection.CUSTOM
        assert item.command_name == "discord"
        assert item.source_name == "!discord"
        assert item.min_role == "everyone"
        assert item.source_enabled is True

    def test_cooldown_takes_the_larger_of_the_two(self):
        (item,) = StreamElementsSource._map_custom(
            se_command(cooldown={"user": 30, "global": 5}), set()
        )
        assert item.cooldown == 30
        assert any("合併" in n for n in item.notes)
        assert item.status is ImportStatus.REVIEW

    def test_equal_cooldowns_need_no_note(self):
        (item,) = StreamElementsSource._map_custom(
            se_command(cooldown={"user": 15, "global": 15}), set()
        )
        assert item.cooldown == 15
        assert item.status is ImportStatus.OK

    def test_aliases_are_normalised_and_deduped(self):
        (item,) = StreamElementsSource._map_custom(
            se_command(command="donate", aliases=["Tip", "donations", "donate"]), set()
        )
        assert item.aliases == ["tip", "donations"]

    def test_keywords_fan_out_into_a_trigger(self):
        command, trigger = StreamElementsSource._map_custom(
            se_command(command="bingbong", keywords=["bing bong", "bingbong!"]), set()
        )
        assert command.section is ImportSection.CUSTOM
        assert trigger.section is ImportSection.TRIGGER
        assert trigger.pattern == "bing bong"
        assert trigger.aliases == ["bingbong!"]
        assert trigger.match_type == "contains"

    def test_single_keyword_produces_no_alias_note(self):
        _, trigger = StreamElementsSource._map_custom(se_command(keywords=["only one"]), set())
        assert trigger.aliases == []

    def test_mention_type_prefixes_the_user(self):
        (item,) = StreamElementsSource._map_custom(se_command(type="mention", reply="歡迎"), set())
        assert item.response == "$(user) 歡迎"

    def test_mention_type_does_not_double_prefix(self):
        (item,) = StreamElementsSource._map_custom(
            se_command(type="mention", reply="${user} 歡迎"), set()
        )
        assert item.response == "$(user) 歡迎"

    def test_whisper_type_is_unsupported(self):
        (item,) = StreamElementsSource._map_custom(se_command(type="whisper"), set())
        assert item.section is ImportSection.UNSUPPORTED

    def test_point_cost_is_unsupported(self):
        (item,) = StreamElementsSource._map_custom(se_command(cost=100), set())
        assert item.section is ImportSection.UNSUPPORTED
        assert any("點數" in n for n in item.notes)

    def test_conflicting_name_is_flagged_not_dropped(self):
        (item,) = StreamElementsSource._map_custom(se_command(command="uptime"), set())
        assert item.status is ImportStatus.CONFLICT
        assert item.section is ImportSection.CUSTOM

    def test_unsupported_command_produces_no_trigger(self):
        items = StreamElementsSource._map_custom(
            se_command(reply="$(customapi https://x)", keywords=["kw"]), set()
        )
        assert len(items) == 1
        assert items[0].section is ImportSection.UNSUPPORTED

    def test_disabled_source_command_keeps_its_state(self):
        (item,) = StreamElementsSource._map_custom(se_command(enabled=False), set())
        assert item.source_enabled is False


class TestStreamElementsDefaults:
    def test_disabled_defaults_are_skipped_entirely(self):
        assert StreamElementsSource._map_default({"command": "points", "enabled": False}) is None

    def test_default_with_an_equivalent_maps_to_a_builtin(self):
        item = StreamElementsSource._map_default({"command": "followage", "enabled": True})
        assert item is not None
        assert item.section is ImportSection.BUILTIN
        assert item.builtin_target == "followage"

    def test_platform_feature_is_listed_as_unsupported(self):
        item = StreamElementsSource._map_default({"command": "songrequest", "enabled": True})
        assert item is not None
        assert item.section is ImportSection.UNSUPPORTED
        assert item.builtin_target is None


# ---------------------------------------------------------------------------
# Nightbot payload mapping
# ---------------------------------------------------------------------------


def nb_command(**overrides) -> dict:
    base = {
        "name": "!discord",
        "message": "加入我們 https://discord.gg/example",
        "userLevel": "everyone",
        "coolDown": 30,
        "count": 0,
    }
    return {**base, **overrides}


class TestNightbotMapping:
    def test_plain_command(self):
        item = NightbotSource._map_custom(nb_command(), set())
        assert item.section is ImportSection.CUSTOM
        assert item.command_name == "discord"
        assert item.cooldown == 30

    def test_alias_becomes_a_redirect(self):
        item = NightbotSource._map_custom(
            nb_command(name="!scores", alias="!moontaku", message=""), set()
        )
        assert item.response == "!moontaku"
        assert item.section is ImportSection.CUSTOM
        assert any("轉呼叫" in n for n in item.notes)

    def test_alias_carries_its_arguments(self):
        item = NightbotSource._map_custom(
            nb_command(name="!setmulti", alias="!multi", message="twitch.tv/nii"), set()
        )
        assert item.response == "!multi twitch.tv/nii"

    def test_redacted_message_is_refused(self):
        # The unauthenticated read replaces variables with [name] markers. If we
        # ever see those on an authenticated read, importing would save a
        # command whose text is permanently broken.
        item = NightbotSource._map_custom(
            nb_command(message="[user] has mined [customapi] coins"), set()
        )
        assert item.section is ImportSection.UNSUPPORTED
        assert any("還原" in n for n in item.notes)

    def test_owner_level_becomes_broadcaster(self):
        item = NightbotSource._map_custom(nb_command(userLevel="owner"), set())
        assert item.min_role == "broadcaster"

    def test_conflicting_name_is_flagged(self):
        item = NightbotSource._map_custom(nb_command(name="!uptime"), set())
        assert item.status is ImportStatus.CONFLICT

    def test_zero_cooldown_becomes_none(self):
        item = NightbotSource._map_custom(nb_command(coolDown=0), set())
        assert item.cooldown is None
