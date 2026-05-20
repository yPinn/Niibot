"""Event logging for Discord server events."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
from datetime import UTC, datetime

import discord
from cachetools import LRUCache
from discord import app_commands
from discord.ext import commands

from core import DATA_DIR, EmbedFactory, load_json, render_message_image

LOGGER: logging.Logger = logging.getLogger(__name__)

_LOG_CHANNELS_FILE = DATA_DIR / "log_channels.json"
_MSG_CACHE_SIZE = 2000  # max cached messages across all guilds


def _load_log_channels() -> dict[int, int]:
    try:
        with open(_LOG_CHANNELS_FILE, encoding="utf-8") as f:
            return {int(k): int(v) for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}


def _save_log_channels(data: dict[int, int]) -> None:
    payload = json.dumps({str(k): v for k, v in data.items()}, ensure_ascii=False, indent=2)
    dir_ = _LOG_CHANNELS_FILE.parent
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_, encoding="utf-8", delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    os.replace(tmp_path, _LOG_CHANNELS_FILE)


def _top_role_color(member: discord.Member) -> tuple[int, int, int] | None:
    """Return the member's top coloured role as an RGB tuple, or None."""
    for role in reversed(member.roles):
        if role.color.value:
            return (role.color.r, role.color.g, role.color.b)
    return None


async def _find_deleter(
    guild: discord.Guild,
    channel_id: int,
    author_id: int,
) -> discord.Member | discord.User | None:
    """Query audit log to find who deleted a message. Returns None on self-delete or no permission."""
    await asyncio.sleep(1.5)
    try:
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.message_delete):
            extra_channel = getattr(entry.extra, "channel", None)
            if (
                entry.target
                and entry.target.id == author_id
                and extra_channel is not None
                and getattr(extra_channel, "id", None) == channel_id
                and (datetime.now(UTC) - entry.created_at).total_seconds() < 15
            ):
                return entry.user
    except discord.Forbidden:
        pass
    return None


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log_channels: dict[int, int] = _load_log_channels()
        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))
        self._msg_cache: LRUCache[int, discord.Message] = LRUCache(maxsize=_MSG_CACHE_SIZE)
        self._log_skip_ids: set[int] = set()

    def skip_delete_log(self, message_id: int) -> None:
        """Register a message ID to be excluded from the next delete log entry."""
        self._log_skip_ids.add(message_id)

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

    # ── Event listeners ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        self._msg_cache[message.id] = message

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if message.id in self._log_skip_ids:
            self._log_skip_ids.discard(message.id)
            return

        log_channel = self.get_log_channel(message.guild)
        if not log_channel or log_channel == message.channel:
            return

        cached = self._msg_cache.pop(message.id, message)
        content_available = bool(cached.content or cached.attachments)

        deleter = await _find_deleter(message.guild, message.channel.id, message.author.id)

        channel_ref = (
            message.channel.mention if hasattr(message.channel, "mention") else str(message.channel)
        )
        sent_at = cached.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        deleted_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        embed = self._embed.build(
            title="訊息刪除",
            color=discord.Color.orange(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="作者", value=cached.author.mention, inline=True)
        embed.add_field(name="頻道", value=channel_ref, inline=True)
        if deleter and deleter.id != cached.author.id:
            embed.add_field(name="刪除者", value=deleter.mention, inline=True)
        else:
            embed.add_field(name="刪除者", value="本人", inline=True)
        embed.add_field(name="發送時間", value=sent_at, inline=True)
        embed.add_field(name="刪除時間", value=deleted_at, inline=True)
        if cached.attachments:
            names = "\n".join(a.filename for a in cached.attachments[:5])
            embed.add_field(name="附件", value=names, inline=False)
        if not content_available:
            embed.add_field(
                name="⚠️ 訊息內容",
                value="無法取得（訊息於 bot 快取範圍外發送）",
                inline=False,
            )

        if not content_available or not cached.content:
            await self._send_log(log_channel, embed)
            return

        author = cached.author
        avatar_url = author.display_avatar.url if author.display_avatar else None
        local_dt = cached.created_at.astimezone()
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
            image_bytes = await render_message_image(
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
            image_bytes = None

        await self._send_log(log_channel, embed, image_bytes)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or not before.guild or before.content == after.content:
            return

        log_channel = self.get_log_channel(before.guild)
        if not log_channel or log_channel == before.channel:
            return

        if after.id in self._msg_cache:
            self._msg_cache[after.id] = after

        channel_ref = (
            before.channel.mention if hasattr(before.channel, "mention") else str(before.channel)
        )

        embed = self._embed.build(
            title="訊息編輯",
            url=after.jump_url,
            color=discord.Color.blue(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="作者", value=before.author.mention, inline=True)
        embed.add_field(name="頻道", value=channel_ref, inline=True)
        embed.add_field(name="編輯前", value=before.content[:1024] or "無內容", inline=False)
        embed.add_field(name="編輯後", value=after.content[:1024] or "無內容", inline=False)

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        log_channel = self.get_log_channel(before.guild)
        if not log_channel:
            return

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

        embed = self._embed.build(
            title="成員資訊更新",
            description=f"{after.mention} (`{after}`)",
            color=discord.Color.purple(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="變更內容", value="\n".join(changes), inline=False)

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return

        guild = messages[0].guild
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        for msg in messages:
            self._msg_cache.pop(msg.id, None)

        channel_ref = (
            messages[0].channel.mention
            if hasattr(messages[0].channel, "mention")
            else str(messages[0].channel)
        )

        embed = self._embed.build(
            title="批量訊息刪除",
            description=f"在 {channel_ref} 刪除了 {len(messages)} 則訊息",
            color=discord.Color.red(),
            timestamp=datetime.now(UTC),
        )

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        joined = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        created = member.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        embed = self._embed.build(
            title="成員加入",
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.green(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="帳號建立時間", value=created, inline=True)
        embed.add_field(name="加入時間", value=joined, inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        banner: discord.Member | discord.User | None = None
        await asyncio.sleep(1.0)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if (
                    entry.target
                    and entry.target.id == user.id
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
                ):
                    banner = entry.user
                    reason = entry.reason or "無"
                    break
            else:
                reason = "無"
        except discord.Forbidden:
            reason = "無"

        embed = self._embed.build(
            title="成員被封禁",
            description=f"{user.mention} (`{user}`)",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(UTC),
        )
        if banner:
            embed.add_field(name="執行者", value=banner.mention, inline=True)
        embed.add_field(name="原因", value=reason, inline=True)
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        log_channel = self.get_log_channel(guild)
        if not log_channel:
            return

        unbanner: discord.Member | discord.User | None = None
        await asyncio.sleep(1.0)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if (
                    entry.target
                    and entry.target.id == user.id
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
                ):
                    unbanner = entry.user
                    break
        except discord.Forbidden:
            pass

        embed = self._embed.build(
            title="成員解除封禁",
            description=f"{user.mention} (`{user}`)",
            color=discord.Color.teal(),
            timestamp=datetime.now(UTC),
        )
        if unbanner:
            embed.add_field(name="執行者", value=unbanner.mention, inline=True)
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        await self._send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        log_channel = self.get_log_channel(member.guild)
        if not log_channel:
            return

        # Check audit log to distinguish voluntary leave from kick (1s delay for propagation)
        await asyncio.sleep(1.0)
        kicker: discord.Member | discord.User | None = None
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and (datetime.now(UTC) - entry.created_at).total_seconds() < 10
                ):
                    kicker = entry.user
                    break
        except discord.Forbidden:
            pass

        joined = (
            member.joined_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if member.joined_at
            else "不明"
        )
        left = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        roles = [r for r in member.roles if r.name != "@everyone"]

        title = "成員被踢出" if kicker else "成員離開"
        embed = self._embed.build(
            title=title,
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now(UTC),
        )
        if kicker:
            embed.add_field(name="執行者", value=kicker.mention, inline=True)
        embed.add_field(name="加入時間", value=joined, inline=True)
        embed.add_field(name="離開時間", value=left, inline=True)
        if roles:
            embed.add_field(
                name="身分組",
                value=", ".join(r.mention for r in roles[:10]),
                inline=False,
            )

        await self._send_log(log_channel, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
