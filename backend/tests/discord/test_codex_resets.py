from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.codex_resets._embeds import (
    build_reset_embed,
    build_scheduled_embed,
    build_status_embed,
    build_watch_embed,
    clean_text,
    limit_markdown,
)
from cogs.codex_resets._state import CodexState, GuildConfig, StateStore, TrackedPost
from cogs.codex_resets.cog import CodexResetsCog
from core import EmbedFactory

FACTORY = EmbedFactory({})


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

    def test_banked_has_hint(self):
        embed = build_reset_embed(FACTORY, _reset("1", kind="banked"))
        assert embed.title == "Codex 儲存額度已發放"
        assert "可自行決定何時使用" in (embed.description or "")

    def test_observed_hides_reply_snippet(self):
        reset = _reset("observed-1", text="@theo Shhhhhh", source={"type": "observed"})
        embed = build_reset_embed(FACTORY, reset)
        assert embed.title == "Codex 額度已重置（觀測）"
        assert "Shhhhhh" not in (embed.description or "")
        assert embed.url is None


class TestOtherEmbeds:
    def test_scheduled_without_time(self):
        sched = {**_reset("5"), "status": "scheduled", "scheduled_for": None}
        assert "預定時間未公布" in (build_scheduled_embed(FACTORY, sched).description or "")
        assert build_scheduled_embed(FACTORY, sched, "done").title == "Codex 重置預告（已執行）"

    def test_watch_with_null_chance(self):
        embed = build_watch_embed(FACTORY, _watch(reset_chance_percent=None))
        assert "機率" not in (embed.description or "")

    def test_status_tolerates_null_stats(self):
        embed = build_status_embed(FACTORY, _status())
        assert embed.description == "尚無重置紀錄"


# ── state ──────────────────────────────────────────────────────────────────


def test_state_roundtrip(tmp_path: Path):
    store = StateStore(tmp_path / "s.json")
    state = CodexState(
        guilds={1: GuildConfig(10, watch=True)},
        seen_ids=["a"],
        scheduled=TrackedPost("s", {"id": "s"}, [(10, 99)]),
    )
    store.save(state)
    assert store.load() == state


def test_state_missing_file_is_unseeded(tmp_path: Path):
    assert StateStore(tmp_path / "none.json").load().seen_ids is None


# ── poll processing ────────────────────────────────────────────────────────


@pytest.fixture
def cog(tmp_path: Path) -> CodexResetsCog:
    c = CodexResetsCog(MagicMock(), store=StateStore(tmp_path / "state.json"))
    c._state.guilds = {1: GuildConfig(10), 2: GuildConfig(20, watch=True)}
    c._send = AsyncMock(return_value=[(10, 100)])  # type: ignore[method-assign]
    c._edit = AsyncMock()  # type: ignore[method-assign]
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
    assert cog._send.await_args.args[0].title == "Codex 額度已重置"


async def test_late_backfill_is_recorded_silently(cog: CodexResetsCog):
    cog._state.seen_ids = ["1"]
    await cog.process(_status(), [_reset("old", ago=timedelta(days=10)), _reset("1")])
    cog._send.assert_not_called()
    assert "old" in (cog._state.seen_ids or [])


async def test_scheduled_then_executed(cog: CodexResetsCog):
    cog._state.seen_ids = []
    sched = {**_reset("5"), "status": "scheduled", "scheduled_for": None}
    await cog.process(_status(scheduled=sched), [])
    assert cog._send.await_args.args[0].title == "Codex 重置預告"

    await cog.process(_status(), [_reset("5")])
    assert cog._edit.await_args.args[1].title == "Codex 重置預告（已執行）"
    assert cog._send.await_args.args[0].title == "Codex 額度已重置"
    assert cog._state.scheduled is None


async def test_watch_goes_to_opted_in_guilds_and_ends(cog: CodexResetsCog):
    cog._state.seen_ids = []
    await cog.process(_status(watch=_watch()), [])
    assert cog._send.await_args.kwargs == {"watch_only": True}

    await cog.process(_status(watch=_watch(level="strong")), [])
    assert "強烈" in (cog._edit.await_args.args[1].description or "")

    await cog.process(_status(), [])
    assert cog._edit.await_args.args[1].title == "Codex 重置觀察（已結束）"
    assert cog._state.watch is None
