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
    def test_strips_trailing_media_links_and_blank_lines(self):
        assert clean_text("Hi.\n\nIt is done. https://t.co/x https://t.co/y") == "Hi.\nIt is done."

    def test_truncates_long_text(self):
        out = clean_text("a" * 500, limit=10)
        assert out == "a" * 10 + "…"

    def test_keeps_inline_links(self):
        assert clean_text("see https://t.co/x now") == "see https://t.co/x now"


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
        assert out == "we have reset rate…"

    def test_unpaired_single_star_escaped(self):
        assert limit_markdown("a *b") == r"a \*b"


class TestResetEmbed:
    def test_regular_quotes_text_without_emoji_chrome(self):
        embed = build_reset_embed(FACTORY, _reset("1"))
        assert embed.title == "Codex 額度已重置"
        assert embed.description == "> Reset all propagated. Enjoy."
        assert embed.url == "https://x.com/t/status/1"
        assert embed.footer.text == "Data from Codex Resets"
        assert embed.thumbnail.url is None

    def test_poster_is_the_author_row(self):
        embed = build_reset_embed(FACTORY, _reset("1"))
        assert embed.author.name == "@thsottiaux"
        assert embed.author.url == "https://x.com/thsottiaux"
        assert embed.author.icon_url == "https://codex-resets.com/thsottiaux-avatar.jpg"

    def test_other_poster_has_no_borrowed_avatar(self):
        reset = _reset("1", source={"type": "x_post", "author": "OpenAI", "url": "https://x"})
        embed = build_reset_embed(FACTORY, reset)
        assert embed.author.name == "@OpenAI"
        assert embed.author.icon_url is None

    def test_facts_fit_one_inline_row(self):
        embed = build_reset_embed(FACTORY, _reset("1"))
        fields = _fields(embed)
        assert list(fields) == ["類型", "公告時間"]
        assert all(f.inline for f in embed.fields)
        assert fields["類型"] == "**全面重置**"
        assert ":f>\n-# <t:" in fields["公告時間"] and fields["公告時間"].endswith(":R>")

    def test_guild_timezone_renders_absolute_time(self):
        reset = {**_reset("1"), "announced_at": "2026-10-07T03:35:09.000Z"}
        embed = build_reset_embed(FACTORY, reset, ZoneInfo("Asia/Taipei"))
        assert _fields(embed)["公告時間"].startswith("2026-10-07 11:35 (UTC+8)\n-# <t:")

    def test_banked_hint_is_a_separate_section(self):
        embed = build_reset_embed(FACTORY, _reset("1", kind="banked"))
        assert embed.title == "Codex 儲存額度已發放"
        assert embed.description == (
            "> Reset all propagated. Enjoy.\n\n-# 額度存入帳戶，可自行決定何時使用"
        )
        assert _fields(embed)["類型"] == "**儲存額度**"

    def test_observed_hides_reply_snippet(self):
        reset = _reset("observed-1", text="@theo Shhhhhh", source={"type": "observed"})
        embed = build_reset_embed(FACTORY, reset)
        assert embed.title == "Codex 額度已重置（觀測）"
        assert "Shhhhhh" not in (embed.description or "")
        assert embed.url is None
        assert embed.author.name == "Codex Resets"


class TestFormatZone:
    @pytest.mark.parametrize(
        ("zone", "expected"),
        [
            ("UTC", "2026-01-15 12:00 (UTC+0)"),
            ("Asia/Kolkata", "2026-01-15 17:30 (UTC+5:30)"),
            ("America/Los_Angeles", "2026-01-15 04:00 (UTC-8)"),
        ],
    )
    def test_offset_label(self, zone: str, expected: str):
        dt = datetime(2026, 1, 15, 12, tzinfo=UTC)
        assert format_zone(dt, ZoneInfo(zone)) == expected

    def test_dst_offset(self):
        dt = datetime(2026, 7, 15, 12, tzinfo=UTC)
        assert format_zone(dt, ZoneInfo("America/Los_Angeles")) == "2026-07-15 05:00 (UTC-7)"


class TestOtherEmbeds:
    def test_scheduled_fields_fill_one_row(self):
        sched = {**_reset("5", kind="banked"), "status": "scheduled", "scheduled_for": None}
        pending = build_scheduled_embed(FACTORY, sched)
        assert _fields(pending) == {
            "預定時間": "未公布",
            "類型": "儲存額度",
            "狀態": "**等待執行**",
        }
        assert (pending.description or "").endswith("\n\n-# 實際執行後會另行通知")

        done = build_scheduled_embed(FACTORY, sched, "done")
        assert done.title == "Codex 重置預告（已執行）"
        assert _fields(done)["狀態"] == "**已執行**"
        assert "另行通知" not in (done.description or "")

    def test_scheduled_time_uses_guild_zone(self):
        sched = {**_reset("5"), "scheduled_for": "2026-10-08T07:00:00Z"}
        embed = build_scheduled_embed(FACTORY, sched, tz=ZoneInfo("Asia/Tokyo"))
        assert _fields(embed)["預定時間"].startswith("2026-10-08 16:00 (UTC+9)")

    def test_watch_fields(self):
        embed = build_watch_embed(FACTORY, _watch())
        fields = _fields(embed)
        assert list(fields) == ["觀察等級", "預估時段", "有效至"]
        assert fields["觀察等級"] == "**升高** · 60%"
        assert fields["預估時段"] == "next 24h"
        assert embed.author.name == "Codex Resets"

    def test_watch_with_null_chance(self):
        embed = build_watch_embed(FACTORY, _watch(reset_chance_percent=None))
        assert _fields(embed)["觀察等級"] == "**升高**"

    def test_ended_watch_drops_expiry(self):
        assert "有效至" not in _fields(build_watch_embed(FACTORY, _watch(), ended=True))

    def test_status_tolerates_null_stats(self):
        embed = build_status_embed(FACTORY, _status())
        assert embed.description == "尚無重置紀錄"
        assert embed.fields == []

    def test_status_sections(self):
        data = _status(scheduled={**_reset("5"), "scheduled_for": _iso(-timedelta(hours=2))})
        data["latest_reset"] = _reset("4", kind="banked", ago=timedelta(days=3))
        data["stats"] = {"total": 12, "avg_interval_days": 9.0, "days_since_last": 3.0}
        embed = build_status_embed(FACTORY, data)

        fields = _fields(embed)
        assert list(fields) == ["上次重置", "下一次", "統計"]
        assert all(f.inline for f in embed.fields)
        assert fields["上次重置"].startswith("**[儲存額度](https://x.com/t/status/4)**\n<t:")
        assert fields["下一次"].startswith("**官方預告**\n<t:")
        assert fields["統計"] == "累計 **12** 次\n平均 **9.0** 天一次\n-# 距上次 3.0 天"
        assert embed.description is None
        assert embed.url == "https://codex-resets.com"

    def test_status_has_no_estimate_without_recent_history(self):
        data = _status()
        data["stats"] = {"total": 3, "avg_interval_days": 10.0, "days_since_last": 4.0}
        assert "下一次" not in _fields(build_status_embed(FACTORY, data))

    def test_status_estimate_uses_recent_median(self):
        # Gaps 1, 3, 3, 30 days: mean 9.25 would mislead, median is 3.
        recent = [_reset(str(i), ago=timedelta(days=d)) for i, d in enumerate((1, 2, 5, 8, 38))]
        data = _status()
        data["stats"] = {"total": 5, "avg_interval_days": 9.25, "days_since_last": 1.0}
        fields = _fields(build_status_embed(FACTORY, data, recent=recent))
        assert fields["下一次"] == "約 **2.0** 天內\n-# 依近 4 次間隔中位數推算，非官方資訊"
        assert "近期約 **3.0** 天一次" in fields["統計"]

    def test_status_overdue_against_median(self):
        recent = [_reset(str(i), ago=timedelta(days=d)) for i, d in enumerate((5, 6, 7, 8))]
        data = _status()
        data["stats"] = {"total": 4, "days_since_last": 5.0}
        assert _fields(build_status_embed(FACTORY, data, recent=recent))["下一次"].startswith(
            "已超過近期中位數\n-# 近 3 次中位數 1.0 天"
        )


class TestRecentMedianGap:
    def test_needs_three_gaps(self):
        assert recent_median_gap([_reset("a"), _reset("b", ago=timedelta(days=1))]) is None
        assert recent_median_gap(None) is None

    def test_order_independent(self):
        recent = [_reset(str(d), ago=timedelta(days=d)) for d in (0, 4, 1, 2)]
        assert recent_median_gap(recent) == pytest.approx((1.0, 3))


class TestReminderEmbed:
    def test_layout(self):
        sched = {**_reset("5", kind="banked"), "scheduled_for": "2026-10-08T07:00:00Z"}
        embed = build_reminder_embed(FACTORY, sched, 30, ZoneInfo("Asia/Taipei"))
        assert embed.title == "Codex 重置即將執行"
        assert embed.author.name == "@thsottiaux"
        assert (embed.description or "").endswith("\n\n-# 提前 30 分鐘提醒")
        fields = _fields(embed)
        assert fields["預定時間"].startswith("2026-10-08 15:00 (UTC+8)")
        assert fields["類型"] == "儲存額度"
        assert [label for label, _ in reminder_links(sched)] == ["查看公告", "Codex Resets"]


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


class TestLinks:
    def test_reset_links_to_post_and_codex(self):
        assert reset_links(_reset("1")) == [
            ("查看公告", "https://x.com/t/status/1"),
            ("開啟 Codex", CODEX_URL),
        ]

    def test_observed_reset_hides_unrelated_reply(self):
        reset = _reset("o", source={"type": "observed", "url": "https://x.com/reply"})
        assert reset_links(reset) == [("開啟 Codex", CODEX_URL), ("Codex Resets", SITE_URL)]

    @pytest.mark.parametrize(
        ("state", "labels"),
        [
            ("pending", ["查看公告", "Codex Resets"]),
            ("done", ["查看公告", "開啟 Codex"]),
            ("ended", ["查看公告"]),
        ],
    )
    def test_scheduled_cta_follows_state(self, state: str, labels: list[str]):
        links = scheduled_links({**_reset("5"), "scheduled_for": None}, state)  # type: ignore[arg-type]
        assert [label for label, _ in links] == labels

    def test_watch_and_status_links(self):
        assert [label for label, _ in watch_links(_watch())] == ["觀察依據", "Codex Resets"]
        assert [label for label, _ in status_links(_status())] == ["開啟 Codex", "Codex Resets"]

    async def test_link_view_is_link_buttons_only(self):
        view = link_view([("查看公告", "https://x"), ("開啟 Codex", CODEX_URL)])
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
    assert cog._send.await_args.args[0](None).title == "Codex 額度已重置"


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
    assert edit_build(None).title == "Codex 重置預告（已執行）"
    assert [label for label, _ in edit_links] == ["查看公告", "開啟 Codex"]
    assert cog._send.await_args.args[0](None).title == "Codex 額度已重置"
    assert cog._state.scheduled is None


async def test_watch_goes_to_opted_in_guilds_and_ends(cog: CodexResetsCog):
    cog._state.seen_ids = []
    await cog.process(_status(watch=_watch()), [])
    assert cog._send.await_args.kwargs == {"watch_only": True}

    await cog.process(_status(watch=_watch(level="strong")), [])
    assert _fields(cog._edit.await_args.args[1](None))["觀察等級"].startswith("**強烈**")

    await cog.process(_status(), [])
    assert cog._edit.await_args.args[1](None).title == "Codex 重置觀察（已結束）"
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
    assert embed.title == "Codex 重置即將執行"
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
        "時區：`Asia/Taipei`\n"
        "官方預告提醒：提前 1 小時（`/codex reminder`）\n"
        "AI 觀察通知：關閉（`/codex watch`）"
    )
    assert "關閉" in _settings_summary(GuildConfig(10, reminder_minutes=None)).splitlines()[1]
