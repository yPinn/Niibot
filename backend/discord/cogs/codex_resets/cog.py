"""Codex Resets cog — polls codex-resets.com and posts concise notifications.

Events
------
- New reset (regular / banked / observed)         → every configured channel
- Scheduled reset announced → executed / ended    → every configured channel, edited in place
- Active watch (AI forecast) appears / changes    → only channels with watch enabled
- Scheduled reset time approaching               → reminder reply, per-guild lead time

Each guild may pick a timezone for absolute times, so every send / edit builds
the embed per guild from an ``EmbedFor`` callback.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cache, partial
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import discord
import httpx
from discord import app_commands
from discord.ext import commands, tasks

from core import RUNTIME_DIR, EmbedFactory

from ._embeds import (
    Link,
    ScheduledState,
    build_reminder_embed,
    build_reset_embed,
    build_scheduled_embed,
    build_status_embed,
    build_watch_embed,
    link_view,
    parse_dt,
    reminder_links,
    reset_links,
    scheduled_links,
    status_links,
    watch_links,
)
from ._state import CodexState, GuildConfig, StateStore, TrackedPost

LOGGER: logging.Logger = logging.getLogger(__name__)

API_BASE = "https://codex-resets.com"
POLL_MINUTES = 5
RECENT_RESETS_LIMIT = 10
# Unseen resets older than this are recorded silently (late backfills, not news).
BACKFILL_WINDOW = timedelta(days=3)
STATE_FILE = RUNTIME_DIR / "codex_resets.json"
# Offered in the timezone autocomplete before anything is typed.
COMMON_TIMEZONES = (
    "Asia/Taipei",
    "Asia/Tokyo",
    "Asia/Hong_Kong",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Seoul",
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Australia/Sydney",
)

EmbedFor = Callable[[ZoneInfo | None], discord.Embed]


@cache
def _all_timezones() -> tuple[str, ...]:
    return tuple(sorted(available_timezones()))


def timezone_matches(current: str, limit: int = 25) -> list[str]:
    """Autocomplete: common zones when empty, else case-insensitive substring matches."""
    query = current.strip().lower().replace(" ", "_")
    if not query:
        return list(COMMON_TIMEZONES)[:limit]
    common = [tz for tz in COMMON_TIMEZONES if query in tz.lower()]
    rest = [tz for tz in _all_timezones() if query in tz.lower() and tz not in common]
    return (common + rest)[:limit]


def _reminder_label(minutes: int | None) -> str:
    if not minutes:
        return "關閉"
    return f"提前 {minutes // 60} 小時" if minutes % 60 == 0 else f"提前 {minutes} 分鐘"


def _settings_summary(cfg: GuildConfig) -> str:
    """Current settings plus where to change each (shown after set-channel)."""
    zone = f"`{cfg.timezone}`" if cfg.timezone else "太平洋時間（預設）"
    return "\n".join(
        (
            f"對照時區：{zone}（時間會先依每位成員的 Discord 時區顯示）",
            f"官方預告提醒：{_reminder_label(cfg.reminder_minutes)}（`/codex reminder`）",
            f"AI 觀察通知：{'開啟' if cfg.watch else '關閉'}（`/codex watch`）",
        )
    )


def _watch_key(watch: dict[str, Any]) -> str:
    return f"{watch.get('observed_at')}|{(watch.get('source') or {}).get('url')}"


def _payload_changed(post: TrackedPost, payload: dict[str, Any]) -> bool:
    return json.dumps(post.payload, sort_keys=True) != json.dumps(payload, sort_keys=True)


@app_commands.guild_only()
class CodexResetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, store: StateStore | None = None) -> None:
        self.bot = bot
        self._embed = EmbedFactory.default()
        self._store = store or StateStore(STATE_FILE)
        self._state: CodexState = self._store.load()
        self._http = httpx.AsyncClient(timeout=10.0, headers={"Accept": "application/json"})
        self._etags: dict[str, tuple[str, dict[str, Any]]] = {}
        self._backoff_until = 0.0

    async def cog_load(self) -> None:
        self._poll.start()

    async def cog_unload(self) -> None:
        self._poll.cancel()
        await self._http.aclose()

    # ── HTTP ────────────────────────────────────────────────────────────────

    async def _fetch(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """GET with ETag reuse and Retry-After backoff. None = skip this round."""
        if time.monotonic() < self._backoff_until:
            return None

        cache_key = f"{path}?{sorted((params or {}).items())}"
        cached = self._etags.get(cache_key)
        headers = {"If-None-Match": cached[0]} if cached else {}

        resp = await self._http.get(f"{API_BASE}{path}", params=params, headers=headers)
        if resp.status_code == 304 and cached:
            return cached[1]
        if resp.status_code == 429:
            try:
                retry_after = int(resp.headers.get("Retry-After", "300"))
            except ValueError:
                retry_after = 300
            self._backoff_until = time.monotonic() + retry_after
            LOGGER.warning("CodexResets: rate limited, backing off %ds", retry_after)
            return None
        resp.raise_for_status()

        body: dict[str, Any] = resp.json()
        if etag := resp.headers.get("ETag"):
            self._etags[cache_key] = (etag, body)
        return body

    # ── Poll loop ───────────────────────────────────────────────────────────

    @tasks.loop(minutes=POLL_MINUTES)
    async def _poll(self) -> None:
        # Any escaping exception would stop the loop for good.
        try:
            status = await self._fetch("/api/v1/status")
            if status is None:
                return
            recent = await self._fetch("/api/v1/resets", {"limit": RECENT_RESETS_LIMIT})
            if recent is None:
                return
            await self.process(status["data"], recent["data"])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            LOGGER.warning("CodexResets: poll failed: %s", exc)
        except Exception:
            LOGGER.exception("CodexResets: unexpected poll error")

    @_poll.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()

    async def process(self, status: dict[str, Any], recent: list[dict[str, Any]]) -> None:
        state = self._state
        scheduled = status.get("scheduled_reset")
        watch = status.get("active_watch")

        if state.seen_ids is None:
            state.mark_seen([r["id"] for r in recent])
            state.scheduled = TrackedPost(scheduled["id"], scheduled) if scheduled else None
            state.watch = TrackedPost(_watch_key(watch), watch) if watch else None
            self._store.save(state)
            LOGGER.info("CodexResets: seeded state with %d resets", len(recent))
            return

        recent_ids = {r["id"] for r in recent}
        await self._sync_scheduled(scheduled, recent_ids)
        await self._send_reminders(datetime.now(UTC))
        await self._announce_new_resets(recent)
        await self._sync_watch(watch)
        self._store.save(state)

    async def _announce_new_resets(self, recent: list[dict[str, Any]]) -> None:
        seen = set(self._state.seen_ids or [])
        cutoff = datetime.now(UTC) - BACKFILL_WINDOW
        fresh = sorted(
            (r for r in recent if r["id"] not in seen and parse_dt(r["announced_at"]) >= cutoff),
            key=lambda r: r["announced_at"],
        )
        for reset in fresh:
            LOGGER.info("CodexResets: new reset id=%s type=%s", reset["id"], reset["reset_type"])
            await self._send(partial(build_reset_embed, self._embed, reset), reset_links(reset))
        self._state.mark_seen([r["id"] for r in recent])

    async def _sync_scheduled(self, current: dict[str, Any] | None, recent_ids: set[str]) -> None:
        state = self._state
        prev = state.scheduled

        if prev and (current is None or current["id"] != prev.key):
            outcome: ScheduledState = "done" if prev.key in recent_ids else "ended"
            ended = prev.payload
            await self._edit(
                prev,
                lambda tz: build_scheduled_embed(self._embed, ended, outcome, tz),
                scheduled_links(ended, outcome),
            )
            state.scheduled = prev = None

        if current is None:
            return

        def build(tz: ZoneInfo | None) -> discord.Embed:
            return build_scheduled_embed(self._embed, current, tz=tz)

        links = scheduled_links(current)
        if prev is None:
            messages = await self._send(build, links)
            state.scheduled = TrackedPost(current["id"], current, messages)
        elif _payload_changed(prev, current):
            if prev.payload.get("scheduled_for") != current.get("scheduled_for"):
                prev.reminded = []  # moved time → remind again against the new time
            prev.payload = current
            await self._edit(prev, build, links)

    async def _send_reminders(self, now: datetime) -> None:
        """Remind each guild `reminder_minutes` before an announced reset time.

        Driven by the poll loop, so a reminder lands up to POLL_MINUTES late;
        state persists, so a restart neither drops nor repeats one.
        """
        post = self._state.scheduled
        if post is None or not post.payload.get("scheduled_for"):
            return
        due = parse_dt(post.payload["scheduled_for"])
        if now >= due:
            return
        announced = parse_dt(post.payload["announced_at"])
        originals = dict(post.messages)  # channel_id → announcement message_id
        links = reminder_links(post.payload)

        for guild_id, cfg in list(self._state.guilds.items()):
            minutes = cfg.reminder_minutes
            if not minutes or guild_id in post.reminded:
                continue
            remind_at = due - timedelta(minutes=minutes)
            if now < remind_at:
                continue
            post.reminded.append(guild_id)
            # Announced inside the window: the announcement already is the heads-up.
            if announced >= remind_at:
                continue
            embed = build_reminder_embed(self._embed, post.payload, minutes, cfg.zone)
            reply_to = originals.get(cfg.channel_id)
            reference = (
                discord.MessageReference(
                    message_id=reply_to, channel_id=cfg.channel_id, fail_if_not_exists=False
                )
                if reply_to
                else None
            )
            await self._post(guild_id, cfg, embed, link_view(links), reference)

    async def _sync_watch(self, current: dict[str, Any] | None) -> None:
        state = self._state
        prev = state.watch

        if prev and (current is None or _watch_key(current) != prev.key):
            gone = prev.payload
            await self._edit(
                prev,
                lambda tz: build_watch_embed(self._embed, gone, ended=True, tz=tz),
                watch_links(gone),
            )
            state.watch = prev = None

        if current is None:
            return

        def build(tz: ZoneInfo | None) -> discord.Embed:
            return build_watch_embed(self._embed, current, tz=tz)

        links = watch_links(current)
        if prev is None:
            messages = await self._send(build, links, watch_only=True)
            state.watch = TrackedPost(_watch_key(current), current, messages)
        elif _payload_changed(prev, current):
            prev.payload = current
            await self._edit(prev, build, links)

    # ── Discord I/O ─────────────────────────────────────────────────────────

    def _zone_for_channel(self, channel_id: int) -> ZoneInfo | None:
        for cfg in self._state.guilds.values():
            if cfg.channel_id == channel_id:
                return cfg.zone
        return None

    async def _send(
        self, build: EmbedFor, links: list[Link], *, watch_only: bool = False
    ) -> list[tuple[int, int]]:
        view = link_view(links)
        sent: list[tuple[int, int]] = []
        for guild_id, cfg in list(self._state.guilds.items()):
            if watch_only and not cfg.watch:
                continue
            message = await self._post(guild_id, cfg, build(cfg.zone), view)
            if message is not None:
                sent.append((message.channel.id, message.id))
        return sent

    async def _post(
        self,
        guild_id: int,
        cfg: GuildConfig,
        embed: discord.Embed,
        view: discord.ui.View | None,
        reference: discord.MessageReference | None = None,
    ) -> discord.Message | None:
        channel = self.bot.get_channel(cfg.channel_id)
        if not isinstance(channel, discord.TextChannel):
            LOGGER.warning(
                "CodexResets: channel %d unavailable (guild %d)", cfg.channel_id, guild_id
            )
            return None
        # The stubs reject explicit None for view / reference; only pass what is set.
        kwargs: dict[str, Any] = {"embed": embed}
        if view is not None:
            kwargs["view"] = view
        if reference is not None:
            kwargs["reference"] = reference
        try:
            return await channel.send(**kwargs)
        except discord.HTTPException as exc:
            LOGGER.warning("CodexResets: send failed channel=%d: %s", channel.id, exc)
            return None

    async def _edit(self, post: TrackedPost, build: EmbedFor, links: list[Link]) -> None:
        """Re-render embed and buttons (a state change can swap the CTA)."""
        view = link_view(links)
        for channel_id, message_id in post.messages:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                embed = build(self._zone_for_channel(channel_id))
                await channel.get_partial_message(message_id).edit(embed=embed, view=view)
            except discord.HTTPException as exc:
                LOGGER.warning("CodexResets: edit failed message=%d: %s", message_id, exc)

    # ── Slash commands ──────────────────────────────────────────────────────

    codex = app_commands.Group(name="codex", description="Codex 重置通知")

    @codex.command(name="set-channel", description="設定 Codex 重置通知頻道與對照時區")
    @app_commands.describe(
        channel="接收通知的文字頻道",
        timezone="時間下方的對照時區（預設太平洋時間，例如 Asia/Taipei）；不填則沿用目前設定",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        timezone: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError):
                await interaction.response.send_message(
                    f"無效的時區：`{timezone}`，請從清單選擇（例如 `Asia/Taipei`）",
                    ephemeral=True,
                )
                return
        perms = channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            await interaction.response.send_message(
                f"我在 {channel.mention} 缺少「傳送訊息」或「嵌入連結」權限", ephemeral=True
            )
            return

        # Keep the guild's other settings (watch / reminder) when re-pointing.
        cfg = self._state.guilds.setdefault(interaction.guild.id, GuildConfig(channel.id))
        cfg.channel_id = channel.id
        if timezone is not None:
            cfg.timezone = timezone
        self._store.save(self._state)
        await interaction.response.send_message(
            f"已設定 Codex 重置通知頻道：{channel.mention}\n{_settings_summary(cfg)}",
            ephemeral=True,
        )

    @set_channel.autocomplete("timezone")
    async def _timezone_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=tz, value=tz) for tz in timezone_matches(current)]

    @codex.command(name="unset-channel", description="取消 Codex 重置通知")
    @app_commands.checks.has_permissions(administrator=True)
    async def unset_channel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        if self._state.guilds.pop(interaction.guild_id, None) is None:
            await interaction.response.send_message("尚未設定通知頻道", ephemeral=True)
            return
        self._store.save(self._state)
        await interaction.response.send_message("已取消 Codex 重置通知", ephemeral=True)

    @codex.command(name="watch", description="開關重置觀察通知（AI 推測，較頻繁）")
    @app_commands.describe(enabled="是否接收重置觀察通知")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_watch(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild_id is not None
        cfg = self._state.guilds.get(interaction.guild_id)
        if cfg is None:
            await interaction.response.send_message(
                "請先用 `/codex set-channel` 設定通知頻道", ephemeral=True
            )
            return
        cfg.watch = enabled
        self._store.save(self._state)
        await interaction.response.send_message(
            f"重置觀察通知已{'開啟' if enabled else '關閉'}", ephemeral=True
        )

    @codex.command(name="reminder", description="官方預告重置前多久提醒")
    @app_commands.describe(minutes="提前提醒的時間")
    @app_commands.choices(
        minutes=[
            app_commands.Choice(name=label, value=value)
            for label, value in (
                ("關閉", 0),
                ("15 分鐘", 15),
                ("30 分鐘（預設）", 30),
                ("1 小時", 60),
                ("2 小時", 120),
            )
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_reminder(
        self, interaction: discord.Interaction, minutes: app_commands.Choice[int]
    ) -> None:
        assert interaction.guild_id is not None
        cfg = self._state.guilds.get(interaction.guild_id)
        if cfg is None:
            await interaction.response.send_message(
                "請先用 `/codex set-channel` 設定通知頻道", ephemeral=True
            )
            return
        cfg.reminder_minutes = minutes.value or None
        self._store.save(self._state)
        await interaction.response.send_message(
            f"官方預告提醒：{_reminder_label(cfg.reminder_minutes)}", ephemeral=True
        )

    @codex.command(name="status", description="查看目前 Codex 重置狀態")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            body = await self._fetch("/api/v1/status")
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("CodexResets: status fetch failed: %s", exc)
            body = None
        if body is None:
            await interaction.followup.send("暫時無法取得資料，請稍後再試", ephemeral=True)
            return
        # Same params as the poll loop, so this is normally an ETag hit.
        try:
            recent = await self._fetch("/api/v1/resets", {"limit": RECENT_RESETS_LIMIT})
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning("CodexResets: recent resets fetch failed: %s", exc)
            recent = None
        cfg = self._state.guilds.get(interaction.guild_id or 0)
        embed = build_status_embed(
            self._embed,
            body["data"],
            cfg.zone if cfg else None,
            recent["data"] if recent else None,
        )
        view = link_view(status_links(body["data"]))
        if view is None:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed, view=view)
