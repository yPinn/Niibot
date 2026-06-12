"""Embed builders for server event logs.

Each builder takes the cog's :class:`EmbedFactory` plus already-computed display
values (audit-derived strings, GMT+8-formatted times) and only assembles fields,
keeping audit/format logic in the cog.
"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from core import EmbedFactory


def build_delete_embed(
    factory: EmbedFactory,
    *,
    author: discord.Member | discord.User,
    channel_ref: str,
    deleter_value: str,
    sent_at: str,
    deleted_at: str,
    attachments: list[discord.Attachment],
    content_available: bool,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="訊息刪除", color=discord.Color.orange(), timestamp=datetime.now(UTC)
    )
    embed.add_field(name="作者", value=author.mention, inline=True)
    embed.add_field(name="頻道", value=channel_ref, inline=True)
    embed.add_field(name="刪除者", value=deleter_value, inline=True)
    embed.add_field(name="發送時間", value=sent_at, inline=True)
    embed.add_field(name="刪除時間", value=deleted_at, inline=True)
    if attachments:
        names = "\n".join(a.filename for a in attachments[:5])
        embed.add_field(name="附件", value=names, inline=False)
    if not content_available:
        embed.add_field(
            name="⚠️ 訊息內容",
            value="無法取得（訊息於 bot 快取範圍外發送）",
            inline=False,
        )
    return embed


def build_edit_embed(
    factory: EmbedFactory,
    *,
    author: discord.Member | discord.User,
    channel_ref: str,
    jump_url: str,
    before_content: str,
    after_content: str,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="訊息編輯",
        url=jump_url,
        color=discord.Color.blue(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(name="作者", value=author.mention, inline=True)
    embed.add_field(name="頻道", value=channel_ref, inline=True)
    embed.add_field(name="編輯前", value=before_content[:1024] or "無內容", inline=False)
    embed.add_field(name="編輯後", value=after_content[:1024] or "無內容", inline=False)
    return embed


def build_member_update_embed(
    factory: EmbedFactory,
    *,
    member: discord.Member,
    changes: list[str],
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="成員資訊更新",
        description=f"{member.mention} (`{member}`)",
        color=discord.Color.purple(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(name="變更內容", value="\n".join(changes), inline=False)
    return embed


def build_timeout_embed(
    factory: EmbedFactory,
    *,
    member: discord.Member,
    applied: bool,
    executor: str,
    expires: str | None,
    reason: str,
    now: datetime,
) -> discord.Embed:
    if applied:
        embed: discord.Embed = factory.build(
            title="成員禁言",
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.dark_orange(),
            timestamp=now,
        )
        embed.add_field(name="執行者", value=executor, inline=True)
        embed.add_field(name="到期時間", value=expires or "未知", inline=True)
        embed.add_field(name="原因", value=reason, inline=False)
    else:
        embed = factory.build(
            title="解除禁言",
            description=f"{member.mention} (`{member}`)",
            color=discord.Color.teal(),
            timestamp=now,
        )
        embed.add_field(name="執行者", value=executor, inline=True)
        embed.add_field(name="原因", value=reason, inline=False)
    return embed


def build_bulk_delete_embed(
    factory: EmbedFactory,
    *,
    channel_ref: str,
    count: int,
    executor_value: str | None,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="批量訊息刪除",
        description=f"在 {channel_ref} 刪除了 {count} 則訊息",
        color=discord.Color.red(),
        timestamp=datetime.now(UTC),
    )
    if executor_value is not None:
        embed.add_field(name="執行者", value=executor_value, inline=True)
    return embed


def build_join_embed(
    factory: EmbedFactory,
    *,
    member: discord.Member,
    created: str,
    joined: str,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="成員加入",
        description=f"{member.mention} (`{member}`)",
        color=discord.Color.green(),
        timestamp=datetime.now(UTC),
    )
    embed.add_field(name="帳號建立時間", value=created, inline=True)
    embed.add_field(name="加入時間", value=joined, inline=True)
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def build_ban_embed(
    factory: EmbedFactory,
    *,
    user: discord.User,
    banner: discord.Member | discord.User | None,
    reason: str,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
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
    return embed


def build_unban_embed(
    factory: EmbedFactory,
    *,
    user: discord.User,
    unbanner: discord.Member | discord.User | None,
) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title="成員解除封禁",
        description=f"{user.mention} (`{user}`)",
        color=discord.Color.teal(),
        timestamp=datetime.now(UTC),
    )
    if unbanner:
        embed.add_field(name="執行者", value=unbanner.mention, inline=True)
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    return embed


def build_remove_embed(
    factory: EmbedFactory,
    *,
    member: discord.Member,
    kicker: discord.Member | discord.User | None,
    joined: str,
    left: str,
    roles: list[discord.Role],
) -> discord.Embed:
    title = "成員被踢出" if kicker else "成員離開"
    embed: discord.Embed = factory.build(
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
        embed.add_field(name="身分組", value=", ".join(r.mention for r in roles[:10]), inline=False)
    return embed
