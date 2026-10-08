from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import discord
import pytest

from cogs.codex_resets._embeds import (
    CODEX_URL,
    SITE_URL,
    build_reminder_embed,
    build_reset_embed,
    build_scheduled_embed,
    build_status_embed,
    build_watch_embed,
    clean_text,
    format_zone,
    limit_markdown,
    link_view,
    recent_median_gap,
    reminder_links,
    reset_links,
    scheduled_links,
    status_links,
    watch_links,
)
from cogs.codex_resets._state import CodexState, GuildConfig, StateStore, TrackedPost
from cogs.codex_resets.cog import CodexResetsCog, _settings_summary, timezone_matches
from core import EmbedFactory

FACTORY = EmbedFactory({})


def _fields(embed) -> dict[str, str]:
    return {f.name: f.value for f in embed.fields}


def _iso(delta: timedelta = timedelta()) -> str:
    return (datetime.now(UTC) - delta).isoformat().replace("+00:00", "Z")


def _reset(rid: str, *, kind: str = "regular", ago: timedelta = timedelta(), **kw) -> dict:
    return {
        "id": rid,
        "reset_type": kind,
        "announced_at": _iso(ago),
        "text": kw.get("text", "Reset all propagated. Enjoy. https://t.co/abc"),
        "source": kw.get(
            "source",
            {"type": "x_post", "author": "thsottiaux", "url": f"https://x.com/t/status/{rid}"},
        ),
    }


def _watch(**kw) -> dict:
    return {
        "level": "elevated",
        "reset_chance_percent": 60,
        "forecast_window": "next 24h",
        "observed_at": "2026-10-07T00:00:00Z",
        "expires_at": "2026-10-08T00:00:00Z",
        "text": "hmm",
        "source": {"type": "observed", "url": "https://x.com/t/status/9"},
        **kw,
    }


def _status(scheduled=None, watch=None) -> dict:
    return {
        "latest_reset": None,
        "scheduled_reset": scheduled,
        "active_watch": watch,
        "stats": {
            "total": 0,
            "last_reset_at": None,
            "days_since_last": None,
            "avg_interval_days": None,
        },
    }


# ── embeds ─────────────────────────────────────────────────────────────────


class TestCleanText:
    def test_keeps_paragraphs_and_strips_trailing_media(self):
        raw = "Hi.\n\n\nIt is done. https://t.co/x https://t.co/y"
        assert clean_text(raw) == "Hi.\n\nIt is done."

    def test_trims_lines_inside_a_paragraph(self):
        assert clean_text(" a \n b ") == "a\nb"

    def test_keeps_inline_links(self):
        assert clean_text("see https://t.co/x now") == "see https://t.co/x now"

    def test_hard_cut_without_any_boundary(self):
        assert clean_text("a" * 500, limit=10) == "a" * 10 + " …"

    def test_cuts_at_paragraph_end(self):
        text = "A" * 30 + "\n\n" + "B" * 40
        assert clean_text(text, limit=50) == "A" * 30 + " …"

    def test_cuts_at_sentence_end(self):
        text = "One. Two three four. Five six seven eight nine"
        assert clean_text(text, limit=30) == "One. Two three four. …"


class TestLimitMarkdown:
    @pytest.mark.parametrize(
        "text",
        ["**reset** limits", "*really* fast", "~~old~~ new", "run `/fast` now"],
    )
    def test_basic_inline_markdown_passes_through(self, text: str):
        assert limit_markdown(text) == text

    def test_underscores_escaped_outside_urls(self):
        assert limit_markdown("by @wong2__ https://x.com/a_b") == r"by @wong2\_\_ https://x.com/a_b"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("# Big", r"\# Big"),
            ("-# small", r"\-# small"),
            ("> quoted", r"\> quoted"),
            ("ok\n## sub", "ok\n" + r"\## sub"),
        ],
    )
    def test_block_syntax_escaped(self, text: str, expected: str):
        assert limit_markdown(text) == expected

    def test_spoiler_and_code_fence_escaped(self):
        assert limit_markdown("||x|| ```y```") == r"\|\|x\|\| \`\`\`y\`\`\`"

    def test_hashtag_untouched(self):
        assert limit_markdown("#Codex rocks") == "#Codex rocks"

    def test_truncation_drops_unpaired_bold(self):
        out = clean_text("we have **reset rate limits and more", limit=20)
        assert out == "we have reset rate …"

    def test_unpaired_single_star_escaped(self):
        assert limit_markdown("a *b") == r"a \*b"


class TestChrome:
    def test_no_links_or_footer_only_buttons(self):
        embed = build_reset_embed(FACTORY, _reset("1"))
        assert embed.url is None
        assert embed.author.name == "Codex Resets"
        assert embed.author.url is None
        assert embed.author.icon_url == "https://codex-resets.com/thsottiaux-avatar.jpg"
        assert embed.footer.text is None
        assert embed.timestamp is None
        assert embed.thumbnail.url is None

    def test_facts_are_full_width_fields(self):
        embed = build_reset_embed(FACTORY, _reset("1"))
        assert [f.inline for f in embed.fields] == [False, False]


def _desc_lines(embed) -> list[str]:
    return (embed.description or "").split("\n")


class TestResetEmbed:
    def test_title_is_the_notice_and_description_the_original(self):
        reset = {**_reset("1"), "announced_at": "2026-10-07T03:35:09.000Z"}
        embed = build_reset_embed(FACTORY, reset)
        assert embed.title == "Codex 額度已重置，現在就能使用"
        assert embed.description == (
            "-# Tibo (@thsottiaux)\n> Reset all propagated. Enjoy.\n\n-# 2026/10/06 8:35 PM PDT"
        )
        assert embed.color == discord.Color.green()

    def test_banked(self):
        embed = build_reset_embed(FACTORY, _reset("1", kind="banked"))
        assert embed.title == "Codex 儲存額度已入帳，可自行決定何時使用"
        assert _fields(embed)["類型"] == "Banked Reset（儲存額度）"
        assert embed.color == discord.Color.gold()

    def test_unknown_poster_is_credited_by_handle(self):
        reset = _reset("1", source={"type": "x_post", "author": "OpenAI", "url": "https://x"})
        assert _desc_lines(build_reset_embed(FACTORY, reset))[0] == "-# @OpenAI"

    def test_paragraphs_survive_in_the_quote(self):
        embed = build_reset_embed(FACTORY, _reset("1", text="First.\n\nSecond."))
        assert _desc_lines(embed)[1:4] == ["> First.", "> ", "> Second."]

    def test_observed_is_non_official_so_chinese_and_explained(self):
        reset = {
            **_reset("observed-1", text="@theo Shhhhhh", source={"type": "observed"}),
            "announced_at": "2026-09-29T19:00:00.000Z",
        }
        embed = build_reset_embed(FACTORY, reset)
        assert embed.description == (
            "-# 無正式公告，由 Codex Resets 觀測\n\n-# 2026/09/29 12:00 PM PDT"
        )
        assert _fields(embed)["類型"] == "全面重置（觀測）"

    def test_time_field_is_one_line_viewer_local(self):
        reset = {**_reset("1"), "announced_at": "2026-10-07T03:35:09.000Z"}
        value = _fields(build_reset_embed(FACTORY, reset))["生效時間"]
        assert value == "<t:1791344109:d> <t:1791344109:t> · <t:1791344109:R>"

    def test_guild_zone_replaces_the_reference_line(self):
        reset = {**_reset("1"), "announced_at": "2026-10-07T03:35:09.000Z"}
        embed = build_reset_embed(FACTORY, reset, ZoneInfo("Asia/Taipei"))
        assert _desc_lines(embed)[-1] == "-# 2026/10/07 11:35 AM UTC+8"

    def test_pacific_label_follows_dst(self):
        reset = {**_reset("1"), "announced_at": "2026-01-15T12:00:00Z"}
        assert _desc_lines(build_reset_embed(FACTORY, reset))[-1] == "-# 2026/01/15 4:00 AM PST"


class TestFormatZone:
    @pytest.mark.parametrize(
        ("zone", "expected"),
        [
            ("UTC", "2026/01/15 12:00 PM UTC+0"),
            ("Asia/Kolkata", "2026/01/15 5:30 PM UTC+5:30"),
            ("America/Los_Angeles", "2026/01/15 4:00 AM UTC-8"),
        ],
    )
    def test_date_time_then_offset(self, zone: str, expected: str):
        dt = datetime(2026, 1, 15, 12, tzinfo=UTC)
        assert format_zone(dt, ZoneInfo(zone)) == expected

    def test_dst_offset(self):
        dt = datetime(2026, 7, 15, 12, tzinfo=UTC)
        assert format_zone(dt, ZoneInfo("America/Los_Angeles")) == "2026/07/15 5:00 AM UTC-7"


class TestScheduledEmbed:
    def test_pending_without_time(self):
        sched = {**_reset("5", kind="banked"), "status": "scheduled", "scheduled_for": None}
        embed = build_scheduled_embed(FACTORY, sched)
        assert embed.title == "Codex 重置預告"
        assert _desc_lines(embed)[:4] == [
            "### 時間尚未公布",
            "-# 實際執行後會再通知",
            "",
            "-# Tibo (@thsottiaux)",
        ]
        assert _fields(embed) == {"預定時間": "未公布", "類型": "Banked Reset（儲存額度）"}
        assert embed.color == discord.Color.blurple()

    def test_pending_counts_down_in_the_description_only(self):
        sched = {**_reset("5"), "scheduled_for": "2026-10-08T07:00:00Z"}
        embed = build_scheduled_embed(FACTORY, sched)
        lines = _desc_lines(embed)
        assert lines[0] == "### 預計 <t:1791442800:R> 重置"
        assert lines[-1] == "-# 2026/10/08 12:00 AM PDT"
        assert _fields(embed)["預定時間"] == "<t:1791442800:d> <t:1791442800:t>"

    @pytest.mark.parametrize(
        ("state", "title"),
        [("done", "Codex 預告的重置已執行"), ("ended", "Codex 重置預告已取消或過期")],
    )
    def test_settled_states_are_grey_history(self, state: str, title: str):
        sched = {**_reset("5"), "scheduled_for": "2026-10-08T07:00:00Z"}
        embed = build_scheduled_embed(FACTORY, sched, state)  # type: ignore[arg-type]
        assert embed.title == title
        assert embed.color == discord.Color.light_grey()
        assert list(_fields(embed)) == ["預定時間", "類型"]
        assert "###" not in (embed.description or "")


class TestReminderEmbed:
    def test_layout(self):
        sched = {**_reset("5", kind="banked"), "scheduled_for": "2026-10-08T07:00:00Z"}
        embed = build_reminder_embed(FACTORY, sched, 30, ZoneInfo("Asia/Taipei"))
        assert embed.title == "Codex 即將重置"
        assert embed.description == (
            "### 預計 <t:1791442800:R> 重置\n"
            "-# 依官方預告，提前 30 分鐘提醒\n"
            "\n"
            "-# 2026/10/08 3:00 PM UTC+8"
        )
        assert _fields(embed) == {
            "預定時間": "<t:1791442800:d> <t:1791442800:t>",
            "類型": "Banked Reset（儲存額度）",
        }
        assert embed.color == discord.Color.red()


class TestWatchEmbed:
    def test_fields(self):
        embed = build_watch_embed(FACTORY, _watch())
        assert embed.title == "Codex 近期重置機率約 60%"
        assert embed.description == (
            "-# Codex Resets 的 AI 推測，並非 OpenAI 官方承諾\n\n-# 2026/10/07 5:00 PM PDT"
        )
        fields = _fields(embed)
        assert list(fields) == ["預測等級", "預估時段", "有效至"]
        assert fields["預測等級"] == "升高"  # AI forecast: non-official → Chinese only
        assert fields["預估時段"] == "next 24h"
        assert "\n" not in fields["有效至"]
        assert embed.color == discord.Color.purple()

    def test_null_chance(self):
        embed = build_watch_embed(FACTORY, _watch(reset_chance_percent=None))
        assert embed.title == "Codex 近期重置的跡象升高"

    def test_ended(self):
        embed = build_watch_embed(FACTORY, _watch(), ended=True)
        assert embed.title == "Codex 重置預測已結束"
        assert "有效至" not in _fields(embed)
        assert embed.description == "-# Codex Resets 的 AI 推測，並非 OpenAI 官方承諾"
        assert embed.color == discord.Color.light_grey()


class TestStatusEmbed:
    def test_tolerates_null_stats(self):
        embed = build_status_embed(FACTORY, _status())
        assert embed.title == "Codex 重置狀態"
        assert embed.description == "### 目前沒有重置預告"
        assert embed.fields == []

    def test_scheduled_leads(self):
        data = _status(scheduled={**_reset("5"), "scheduled_for": "2026-10-08T07:00:00Z"})
        data["latest_reset"] = _reset("4", kind="banked", ago=timedelta(days=3))
        data["stats"] = {"total": 12, "avg_interval_days": 9.0, "days_since_last": 3.0}
        embed = build_status_embed(FACTORY, data)

        assert _desc_lines(embed) == [
            "### 官方預告 <t:1791442800:R> 重置",
            "-# <t:1791442800:d> <t:1791442800:t> · Full Reset（全面重置）",
            "",
            "-# 2026/10/08 12:00 AM PDT",
        ]
        fields = _fields(embed)
        assert fields["上次重置"].startswith("Banked Reset（儲存額度） · <t:")
        assert fields["統計"] == "累計 12 次 · 平均約 9.0 天一次"

    def test_estimate_uses_recent_median(self):
        # Gaps 1, 3, 3, 30 days: mean 9.25 would mislead, median is 3.
        recent = [_reset(str(i), ago=timedelta(days=d)) for i, d in enumerate((1, 2, 5, 8, 38))]
        data = _status()
        data["stats"] = {"total": 5, "avg_interval_days": 9.25, "days_since_last": 1.0}
        embed = build_status_embed(FACTORY, data, recent=recent)
        assert embed.description == (
            "### 預估約 2.0 天內重置\n-# 尚無官方預告，依近 4 次重置間隔的中位數（3.0 天）推算"
        )
        assert _fields(embed)["統計"] == "累計 5 次 · 近期約 3.0 天一次"

    def test_overdue_against_median(self):
        recent = [_reset(str(i), ago=timedelta(days=d)) for i, d in enumerate((5, 6, 7, 8))]
        data = _status()
        data["stats"] = {"total": 4, "days_since_last": 5.0}
        assert (build_status_embed(FACTORY, data, recent=recent).description or "").startswith(
            "### 隨時可能重置\n-# 尚無官方預告，依近 3 次重置間隔的中位數（1.0 天）"
        )


class TestRecentMedianGap:
    def test_needs_three_gaps(self):
        assert recent_median_gap([_reset("a"), _reset("b", ago=timedelta(days=1))]) is None
        assert recent_median_gap(None) is None

    def test_order_independent(self):
        recent = [_reset(str(d), ago=timedelta(days=d)) for d in (0, 4, 1, 2)]
        assert recent_median_gap(recent) == pytest.approx((1.0, 3))


class TestTimezoneMatches:
    def test_empty_query_offers_common_zones(self):
        assert timezone_matches("")[0] == "Asia/Taipei"

    def test_substring_match_ranks_common_first(self):
        matches = timezone_matches("tai")
        assert matches[0] == "Asia/Taipei"
        assert len(matches) <= 25

    def test_space_matches_underscore(self):
        assert "America/Los_Angeles" in timezone_matches("los ang")


def test_guild_zone_ignores_invalid_names():
    assert GuildConfig(1, timezone="Asia/Taipei").zone == ZoneInfo("Asia/Taipei")
    assert GuildConfig(1, timezone="Mars/Olympus").zone is None
    assert GuildConfig(1).zone is None


# ── link buttons ───────────────────────────────────────────────────────────

SITE = ("Codex Resets", SITE_URL)
CODEX = ("開啟 Codex", CODEX_URL)


class TestLinks:
    def test_every_message_links_the_site(self):
        sched = {**_reset("5"), "scheduled_for": None}
        for links in (
            reset_links(_reset("1")),
            scheduled_links(sched),
            scheduled_links(sched, "done"),
            scheduled_links(sched, "ended"),
            reminder_links(sched),
            watch_links(_watch()),
            status_links(_status()),
        ):
            assert links[-1] == SITE

    def test_reset_links(self):
        assert reset_links(_reset("1")) == [("查看公告", "https://x.com/t/status/1"), CODEX, SITE]

    def test_observed_reset_hides_unrelated_reply(self):
        reset = _reset("o", source={"type": "observed", "url": "https://x.com/reply"})
        assert reset_links(reset) == [CODEX, SITE]

    @pytest.mark.parametrize(
        ("state", "labels"),
        [
            ("pending", ["查看公告", "Codex Resets"]),
            ("done", ["查看公告", "開啟 Codex", "Codex Resets"]),
            ("ended", ["查看公告", "Codex Resets"]),
        ],
    )
    def test_open_codex_only_once_usable(self, state: str, labels: list[str]):
        links = scheduled_links({**_reset("5"), "scheduled_for": None}, state)  # type: ignore[arg-type]
        assert [label for label, _ in links] == labels

    def test_watch_reminder_and_status_links(self):
        sched = {**_reset("5"), "scheduled_for": None}
        assert [label for label, _ in watch_links(_watch())] == ["預測依據", "Codex Resets"]
        assert [label for label, _ in reminder_links(sched)] == ["查看公告", "Codex Resets"]
        assert status_links(_status()) == [CODEX, SITE]

    async def test_link_view_is_link_buttons_only(self):
        view = link_view([("查看公告", "https://x"), CODEX])
        assert view is not None
        assert [(b.label, b.url, b.style) for b in view.children] == [  # type: ignore[attr-defined]
            ("查看公告", "https://x", discord.ButtonStyle.link),
            ("開啟 Codex", CODEX_URL, discord.ButtonStyle.link),
        ]
        assert not view.is_dispatchable()
        assert link_view([]) is None


# ── state ──────────────────────────────────────────────────────────────────


def test_state_roundtrip(tmp_path: Path):
    store = StateStore(tmp_path / "s.json")
    state = CodexState(
        guilds={
            1: GuildConfig(10, watch=True, timezone="Asia/Taipei", reminder_minutes=60),
            2: GuildConfig(20, reminder_minutes=None),
        },
        seen_ids=["a"],
        scheduled=TrackedPost("s", {"id": "s"}, [(10, 99)], reminded=[1]),
    )
    store.save(state)
    assert store.load() == state


def test_legacy_state_gets_default_reminder(tmp_path: Path):
    path = tmp_path / "s.json"
    path.write_text('{"guilds": {"1": {"channel_id": 10}}, "seen_ids": []}', encoding="utf-8")
    assert StateStore(path).load().guilds[1].reminder_minutes == 30


def test_state_missing_file_is_unseeded(tmp_path: Path):
    assert StateStore(tmp_path / "none.json").load().seen_ids is None


# ── poll processing ────────────────────────────────────────────────────────


@pytest.fixture
def cog(tmp_path: Path) -> CodexResetsCog:
    c = CodexResetsCog(MagicMock(), store=StateStore(tmp_path / "state.json"))
    c._state.guilds = {1: GuildConfig(10), 2: GuildConfig(20, watch=True)}
    c._send = AsyncMock(return_value=[(10, 100)])  # type: ignore[method-assign]
    c._edit = AsyncMock()  # type: ignore[method-assign]
    c._post = AsyncMock()  # type: ignore[method-assign]
    return c


async def test_first_poll_seeds_silently(cog: CodexResetsCog):
    await cog.process(_status(watch=_watch()), [_reset("1")])
    cog._send.assert_not_called()
    assert cog._state.seen_ids == ["1"]
    assert cog._state.watch is not None


async def test_new_reset_is_announced_once(cog: CodexResetsCog):
    cog._state.seen_ids = ["1"]
    recent = [_reset("2"), _reset("1", ago=timedelta(days=1))]
    await cog.process(_status(), recent)
    await cog.process(_status(), recent)
    assert cog._send.await_count == 1
    assert cog._send.await_args.args[0](None).title == "Codex 額度已重置，現在就能使用"


async def test_late_backfill_is_recorded_silently(cog: CodexResetsCog):
    cog._state.seen_ids = ["1"]
    await cog.process(_status(), [_reset("old", ago=timedelta(days=10)), _reset("1")])
    cog._send.assert_not_called()
    assert "old" in (cog._state.seen_ids or [])


async def test_scheduled_then_executed(cog: CodexResetsCog):
    cog._state.seen_ids = []
    sched = {**_reset("5"), "status": "scheduled", "scheduled_for": None}
    await cog.process(_status(scheduled=sched), [])
    assert cog._send.await_args.args[0](None).title == "Codex 重置預告"

    await cog.process(_status(), [_reset("5")])
    edit_build, edit_links = cog._edit.await_args.args[1:]
    assert edit_build(None).title == "Codex 預告的重置已執行"
    assert [label for label, _ in edit_links] == ["查看公告", "開啟 Codex", "Codex Resets"]
    assert cog._send.await_args.args[0](None).title == "Codex 額度已重置，現在就能使用"
    assert cog._state.scheduled is None


async def test_watch_goes_to_opted_in_guilds_and_ends(cog: CodexResetsCog):
    cog._state.seen_ids = []
    await cog.process(_status(watch=_watch()), [])
    assert cog._send.await_args.kwargs == {"watch_only": True}

    await cog.process(_status(watch=_watch(level="strong")), [])
    assert _fields(cog._edit.await_args.args[1](None))["預測等級"] == "強烈"

    await cog.process(_status(), [])
    assert cog._edit.await_args.args[1](None).title == "Codex 重置預測已結束"
    assert cog._state.watch is None


# ── scheduled reminders ────────────────────────────────────────────────────

NOW = datetime(2026, 10, 8, 6, 40, tzinfo=UTC)  # 20 min before DUE


def _due_post(*, due: str = "2026-10-08T07:00:00Z", announced: str = "2026-10-07T19:19:33Z"):
    payload = {**_reset("5"), "announced_at": announced, "scheduled_for": due}
    return TrackedPost("5", payload, [(10, 100), (20, 200)])


async def test_reminder_replies_once_per_guild(cog: CodexResetsCog):
    cog._state.guilds[2].reminder_minutes = 15  # not due yet at NOW
    cog._state.scheduled = _due_post()

    await cog._send_reminders(NOW)
    await cog._send_reminders(NOW)

    assert cog._post.await_count == 1
    guild_id, cfg, embed, view, reference = cog._post.await_args.args
    assert (guild_id, cfg.channel_id) == (1, 10)
    assert embed.title == "Codex 即將重置"
    assert (reference.message_id, reference.channel_id) == (100, 10)
    assert cog._state.scheduled.reminded == [1]

    await cog._send_reminders(NOW + timedelta(minutes=6))
    assert cog._post.await_count == 2
    assert cog._state.scheduled.reminded == [1, 2]


async def test_reminder_respects_off_and_not_yet_due(cog: CodexResetsCog):
    cog._state.guilds[1].reminder_minutes = None
    cog._state.guilds[2].reminder_minutes = 15
    cog._state.scheduled = _due_post()
    await cog._send_reminders(NOW)
    cog._post.assert_not_called()


async def test_no_reminder_after_due_or_without_time(cog: CodexResetsCog):
    cog._state.scheduled = _due_post()
    await cog._send_reminders(datetime(2026, 10, 8, 7, 1, tzinfo=UTC))
    cog._state.scheduled = _due_post()
    cog._state.scheduled.payload["scheduled_for"] = None
    await cog._send_reminders(NOW)
    cog._post.assert_not_called()


async def test_announcement_inside_window_is_its_own_reminder(cog: CodexResetsCog):
    cog._state.scheduled = _due_post(announced="2026-10-08T06:45:00Z")
    await cog._send_reminders(datetime(2026, 10, 8, 6, 50, tzinfo=UTC))
    cog._post.assert_not_called()
    assert 1 in cog._state.scheduled.reminded


async def test_reminder_without_original_message_posts_plainly(cog: CodexResetsCog):
    post = _due_post()
    post.messages = []  # seeded at startup: announcement predates the bot
    cog._state.scheduled = post
    await cog._send_reminders(NOW)
    assert cog._post.await_args.args[4] is None


async def test_rescheduled_time_rearms_reminders(cog: CodexResetsCog):
    cog._state.seen_ids = []
    cog._state.scheduled = _due_post()
    cog._state.scheduled.reminded = [1]
    moved = {**cog._state.scheduled.payload, "scheduled_for": "2026-10-09T07:00:00Z"}
    await cog._sync_scheduled(moved, set())
    assert cog._state.scheduled.reminded == []


def test_settings_summary_lists_next_steps():
    summary = _settings_summary(GuildConfig(10, timezone="Asia/Taipei", reminder_minutes=60))
    assert summary == (
        "對照時區：`Asia/Taipei`（時間會先依每位成員的 Discord 時區顯示）\n"
        "官方預告提醒：提前 1 小時（`/codex-config reminder`）\n"
        "AI 重置預測通知：關閉（`/codex-config forecast`）"
    )
    default = _settings_summary(GuildConfig(10, reminder_minutes=None)).splitlines()
    assert default[0].startswith("對照時區：太平洋時間（預設）")
    assert "關閉" in default[1]


# ── command surface ────────────────────────────────────────────────────────


def test_public_read_and_hidden_guild_only_config():
    status = CodexResetsCog.codex
    assert status.name == "codex"
    assert status.guild_only
    assert status.default_permissions is None  # everyone sees /codex

    config = CodexResetsCog.config
    assert config.name == "codex-config"
    assert config.default_permissions == discord.Permissions(manage_guild=True)
    assert config.allowed_contexts is not None
    assert config.allowed_contexts.guild and not config.allowed_contexts.dm_channel
    assert sorted(c.name for c in config.commands) == ["channel", "disable", "forecast", "reminder"]
