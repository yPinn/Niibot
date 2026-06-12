"""EventsCog — listens to server events and posts logs to the configured channel."""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime

import discord
from cachetools import LRUCache, TTLCache
from discord import app_commands
from discord.ext import commands

from core import EmbedFactory, render_message_image

from . import _embeds
from ._audit import _find_audit_entry, _find_deleter
from ._persistence import _load_log_channels, _save_log_channels
from .constants import (
    _PER_GUILD_CACHE_SIZE,
    _SKIP_IDS_MAX,
    _SKIP_IDS_TTL,
    _TZ_GMT8,
    _fmt_local,
    _top_role_color,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log_channels: dict[int, int] = _load_log_channels()
        self._embed = EmbedFactory.default()
        # Per-guild caches so a busy guild can't evict another guild's messages.
        self._msg_cache: dict[int, LRUCache[int, discord.Message]] = {}
        # TTL-bounded so a skip ID whose delete never arrives is auto-reclaimed.
        self._log_skip_ids: TTLCache[int, bool] = TTLCache(maxsize=_SKIP_IDS_MAX, ttl=_SKIP_IDS_TTL)

    def skip_delete_log(self, message_id: int) -> None:
        """Register a message ID to be excluded from the next delete log entry."""
        self._log_skip_ids[message_id] = True

    def _cache_message(self, message: discord.Message) -> None:
        """Store *message* in its guild's bucket, creating the bucket on demand."""
        if message.guild is None:
            return
        bucket = self._msg_cache.get(message.guild.id)
        if bucket is None:
            bucket = LRUCache(maxsize=_PER_GUILD_CACHE_SIZE)
            self._msg_cache[message.guild.id] = bucket
        bucket[message.id] = message

    def _pop_cached(
        self, guild_id: int, message_id: int, default: discord.Message
    ) -> discord.Message:
        """Pop a cached message from its guild bucket, or return *default*."""
        bucket = self._msg_cache.get(guild_id)
        if bucket is None:
            return default
        return bucket.pop(message_id, default)

    # ── Slash command group ──────────────────────────────────────────────────

    log = app_commands.Group(name="log", description="日誌頻道設定")

    @log.command(name="set", description="設定日誌頻道")
    @app_commands.describe(channel="要設定為日誌頻道的文字頻道")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_set(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        self.log_channels[interaction.guild.id] = channel.id
        _save_log_channels(self.log_channels)
        await interaction.response.send_message(
            f"已設定日誌頻道：{channel.mention}", ephemeral=True
        )
        LOGGER.info(
            "Log channel set | Guild: %s | Channel: #%s | By: %s",
            interaction.guild.name,
            channel.name,
            interaction.user.name,
        )

    @log.command(name="unset", description="取消日誌頻道")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_unset(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        if interaction.guild.id in self.log_channels:
            del self.log_channels[interaction.guild.id]
            _save_log_channels(self.log_channels)
            await interaction.response.send_message("已取消日誌頻道設定", ephemeral=True)
            LOGGER.info(
                "Log channel unset | Guild: %s | By: %s",
                interaction.guild.name,
                interaction.user.name,
            )
        else:
            await interaction.response.send_message("尚未設定日誌頻道", ephemeral=True)

    @log.command(name="status", description="查看目前日誌頻道設定")
    async def log_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        channel = self.get_log_channel(interaction.guild)
        if channel:
            await interaction.response.send_message(
                f"目前日誌頻道：{channel.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "尚未設定日誌頻道，請使用 `/log set` 設定", ephemeral=True
            )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self.log_channels.get(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel
        return None

    async def _send_log(
        self,
        log_channel: discord.TextChannel,
        embed: discord.Embed,
        image_bytes: bytes | None = None,
    ) -> None:
        try:
            file = (
                discord.File(io.BytesIO(image_bytes), filename="message.png")
                if image_bytes
                else None
            )
            if file:
                embed.set_image(url="attachment://message.png")
                await log_channel.send(embed=embed, file=file)
            else:
                await log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as e:
            LOGGER.warning("Failed to send log to %s: %s", log_channel.id, e)

    async def _render_delete_image(self, cached: discord.Message) -> bytes | None:
        """Render the deleted message as a Discord-style image, or None on failure."""
        author = cached.author
        avatar_url = author.display_avatar.url if author.display_avatar else None
        local_dt = cached.created_at.astimezone(_TZ_GMT8)
        hour = local_dt.hour
        period = "上午" if hour < 12 else "下午"
        h12 = hour % 12 or 12
        timestamp_str = f"{period} {h12:02d}:{local_dt.minute:02d}"
        role_color: tuple[int, int, int] | None = None
        server_tag: tuple[str, str | None] | None = None
        decoration_url: str | None = None

        user_obj = author._user if isinstance(author, discord.Member) else author
        deco = getattr(user_obj, "avatar_decoration", None)
        if deco is not None:
            decoration_url = deco.url

        if isinstance(author, discord.Member):
            role_color = _top_role_color(author)
            pg = getattr(author._user, "primary_guild", None)
            if pg and getattr(pg, "identity_enabled", False) and pg.tag:
                server_tag = (pg.tag, pg.badge.url if pg.badge else None)

        try:
            image: bytes = await render_message_image(
                avatar_url=avatar_url,
                display_name=author.display_name,
                timestamp_str=timestamp_str,
                content=cached.content,
                role_color=role_color,
                server_tag=server_tag,
                decoration_url=decoration_url,
            )
        except Exception as e:
            LOGGER.warning("Message image render failed: %s", e)
            return None
        return image

    # ── Event listeners ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        self._cache_message(message)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Drop a guild's message-cache bucket when the bot leaves it."""
        self._msg_cache.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if self._log_skip_ids.pop(message.id, None) is not None:
            return

        log_channel = self.get_log_channel(message.guild)
        if not log_channel or log_channel == message.channel:
            return

        cached = self._pop_cached(message.guild.id, message.id, message)
        content_available = bool(cached.content or cached.attachments)

        deleter, audit_available = await _find_deleter(
            message.guild, message.channel.id, message.author.id
        )

        channel_ref = (
            message.channel.mention if hasattr(message.channel, "mention") else str(message.channel)
        )
        if not audit_available:
            deleter_value = "未知（無審核權限）"
        elif deleter and deleter.id != cached.author.id:
            deleter_value = deleter.mention
        else:
            deleter_value = "本人"

        embed = _embeds.build_delete_embed(
            self._embed,
            author=cached.author,
            channel_ref=channel_ref,
            deleter_value=deleter_value,
            sent_at=_fmt_local(cached.created_at),
            deleted_at=_fmt_local(datetime.now(UTC)),
            attachments=cached.attachments,
            content_available=content_available,
        )

        if not content_available or not cached.content:
            await self._send_log(log_channel, embed)
            return

        image_bytes = await self._render_delete_image(cached)
        await self._send_log(log_channel, embed, image_bytes)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or not before.guild or before.content == after.content:
            return

        log_channel = self.get_log_channel(before.guild)
        if not log_channel or log_channel == before.channel:
            return

        bucket = self._msg_cache.get(before.guild.id)
        if bucket is not None and after.id in bucket:
            bucket[after.id] = after

        channel_ref = (
            before.channel.mention if hasattr(before.channel, "mention") else str(before.channel)
        )
        embed = _embeds.build_edit_embed(
            self._embed,
            author=before.author,
            channel_ref=channel_ref,
            jump_url=after.jump_url,
            before_content=before.content,
            after_content=after.content,
        )
        await self._send_log(log_channel, embed)

    async def _log_timeout_change(
        self,
        log_channel: discord.TextChannel,
        after: discord.Member,
    ) -> None:
        """Log a timeout (communication disabled) applied / removed on *after*."""
        now = datetime.now(UTC)
        timeout_until = after.timed_out_until

        entry, audit_available = await _find_audit_entry(
            after.guild,
            discord.AuditLogAction.member_update,
            match=lambda e: bool(e.target and e.target.id == after.id),
        )
        if not audit_available:
            executor = "未知（無審核權限）"
        elif entry and entry.user:
            executor = entry.user.mention
        else:
            # No audit entry usually means the timeout lapsed automatically.
            executor = "自動／未知"
        reason = (entry.reason if entry else None) or "無"

        applied = timeout_until is not None and timeout_until > now
        embed = _embeds.build_timeout_embed(
            self._embed,
            member=after,
            applied=applied,
            executor=executor,
            expires=_fmt_local(timeout_until) if applied and timeout_until else None,
            reason=reason,
            now=now,
        )
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        log_channel = self.get_log_channel(before.guild)
        if not log_channel:
            return

        # Timeout (communication disabled) is a moderation action — log it as its
        # own embed with an executor, independent of nick/role changes below.
        if before.timed_out_until != after.timed_out_until:
            await self._log_timeout_change(log_channel, after)

        changes: list[str] = []

        if before.nick != after.nick:
            changes.append(f"暱稱: `{before.nick or '無'}` → `{after.nick or '無'}`")

        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added:
                changes.append(f"新增身分組: {', '.join(r.mention for r in added)}")
            if removed:
                changes.append(f"移除身分組: {', '.join(r.mention for r in removed)}")

        if not changes:
            return

        embed = _embeds.build_member_update_embed(self._embed, member=after, changes=changes)
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return

        guild = messages[0].guild
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        bucket = self._msg_cache.get(guild.id)
        if bucket is not None:
            for msg in messages:
                bucket.pop(msg.id, None)

        channel = messages[0].channel
        channel_ref = channel.mention if hasattr(channel, "mention") else str(channel)

        entry, audit_available = await _find_audit_entry(
            guild,
            discord.AuditLogAction.message_bulk_delete,
            match=lambda e: bool(e.target and e.target.id == getattr(channel, "id", None)),
        )
        if not audit_available:
            executor_value: str | None = "未知（無審核權限）"
        elif entry and entry.user:
            executor_value = entry.user.mention
        else:
            executor_value = None

        embed = _embeds.build_bulk_delete_embed(
            self._embed,
            channel_ref=channel_ref,
            count=len(messages),
            executor_value=executor_value,
        )
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        embed = _embeds.build_join_embed(
            self._embed,
            member=member,
            created=_fmt_local(member.created_at),
            joined=_fmt_local(datetime.now(UTC)),
        )
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        entry, _ = await _find_audit_entry(
            guild,
            discord.AuditLogAction.ban,
            match=lambda e: bool(e.target and e.target.id == user.id),
        )
        banner = entry.user if entry else None
        reason = (entry.reason if entry else None) or "無"

        embed = _embeds.build_ban_embed(self._embed, user=user, banner=banner, reason=reason)
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        entry, _ = await _find_audit_entry(
            guild,
            discord.AuditLogAction.unban,
            match=lambda e: bool(e.target and e.target.id == user.id),
        )
        unbanner = entry.user if entry else None

        embed = _embeds.build_unban_embed(self._embed, user=user, unbanner=unbanner)
        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        # Check audit log to distinguish a voluntary leave from a kick.
        entry, _ = await _find_audit_entry(
            member.guild,
            discord.AuditLogAction.kick,
            match=lambda e: bool(e.target and e.target.id == member.id),
        )
        kicker = entry.user if entry else None

        roles = [r for r in member.roles if r.name != "@everyone"]
        embed = _embeds.build_remove_embed(
            self._embed,
            member=member,
            kicker=kicker,
            joined=_fmt_local(member.joined_at) if member.joined_at else "不明",
            left=_fmt_local(datetime.now(UTC)),
            roles=roles,
        )
        await self._send_log(log_channel, embed)
