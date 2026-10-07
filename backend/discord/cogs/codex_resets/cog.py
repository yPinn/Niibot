"""Codex Resets cog — polls codex-resets.com and posts concise notifications.

Events
------
- New reset (regular / banked / observed)         → every configured channel
- Scheduled reset announced → executed / ended    → every configured channel, edited in place
- Active watch (AI forecast) appears / changes    → only channels with watch enabled
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import discord
import httpx
from discord import app_commands
from discord.ext import commands, tasks

from core import RUNTIME_DIR, EmbedFactory

from ._embeds import (
    ScheduledState,
    build_reset_embed,
    build_scheduled_embed,
    build_status_embed,
    build_watch_embed,
    parse_dt,
)
from ._state import CodexState, GuildConfig, StateStore, TrackedPost

LOGGER: logging.Logger = logging.getLogger(__name__)

API_BASE = "https://codex-resets.com"
POLL_MINUTES = 5
RECENT_RESETS_LIMIT = 10
# Unseen resets older than this are recorded silently (late backfills, not news).
BACKFILL_WINDOW = timedelta(days=3)
STATE_FILE = RUNTIME_DIR / "codex_resets.json"


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
            await self._send(build_reset_embed(self._embed, reset))
        self._state.mark_seen([r["id"] for r in recent])

    async def _sync_scheduled(self, current: dict[str, Any] | None, recent_ids: set[str]) -> None:
        state = self._state
        prev = state.scheduled

        if prev and (current is None or current["id"] != prev.key):
            outcome: ScheduledState = "done" if prev.key in recent_ids else "ended"
            await self._edit(prev, build_scheduled_embed(self._embed, prev.payload, outcome))
            state.scheduled = prev = None

        if current is None:
            return
        if prev is None:
            messages = await self._send(build_scheduled_embed(self._embed, current))
            state.scheduled = TrackedPost(current["id"], current, messages)
        elif _payload_changed(prev, current):
            prev.payload = current
            await self._edit(prev, build_scheduled_embed(self._embed, current))

    async def _sync_watch(self, current: dict[str, Any] | None) -> None:
        state = self._state
        prev = state.watch

        if prev and (current is None or _watch_key(current) != prev.key):
            await self._edit(prev, build_watch_embed(self._embed, prev.payload, ended=True))
            state.watch = prev = None

        if current is None:
            return
        if prev is None:
            messages = await self._send(build_watch_embed(self._embed, current), watch_only=True)
            state.watch = TrackedPost(_watch_key(current), current, messages)
        elif _payload_changed(prev, current):
            prev.payload = current
            await self._edit(prev, build_watch_embed(self._embed, current))

    # ── Discord I/O ─────────────────────────────────────────────────────────

    async def _send(
        self, embed: discord.Embed, *, watch_only: bool = False
    ) -> list[tuple[int, int]]:
        sent: list[tuple[int, int]] = []
        for guild_id, cfg in list(self._state.guilds.items()):
            if watch_only and not cfg.watch:
                continue
            channel = self.bot.get_channel(cfg.channel_id)
            if not isinstance(channel, discord.TextChannel):
                LOGGER.warning(
                    "CodexResets: channel %d unavailable (guild %d)", cfg.channel_id, guild_id
                )
                continue
            try:
                message = await channel.send(embed=embed)
            except discord.HTTPException as exc:
                LOGGER.warning("CodexResets: send failed channel=%d: %s", channel.id, exc)
                continue
            sent.append((channel.id, message.id))
        return sent

    async def _edit(self, post: TrackedPost, embed: discord.Embed) -> None:
        for channel_id, message_id in post.messages:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                await channel.get_partial_message(message_id).edit(embed=embed)
            except discord.HTTPException as exc:
                LOGGER.warning("CodexResets: edit failed message=%d: %s", message_id, exc)

    # ── Slash commands ──────────────────────────────────────────────────────

    codex = app_commands.Group(name="codex", description="Codex 重置通知")

    @codex.command(name="set-channel", description="設定 Codex 重置通知頻道")
    @app_commands.describe(channel="接收通知的文字頻道")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        assert interaction.guild is not None
        perms = channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            await interaction.response.send_message(
                f"我在 {channel.mention} 缺少「傳送訊息」或「嵌入連結」權限", ephemeral=True
            )
            return

        existing = self._state.guilds.get(interaction.guild.id)
        self._state.guilds[interaction.guild.id] = GuildConfig(
            channel.id, watch=existing.watch if existing else False
        )
        self._store.save(self._state)
        await interaction.response.send_message(
            f"已設定 Codex 重置通知頻道：{channel.mention}", ephemeral=True
        )

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
        await interaction.followup.send(embed=build_status_embed(self._embed, body["data"]))
