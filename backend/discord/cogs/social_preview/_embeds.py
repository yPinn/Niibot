"""Unified embed builder for social media previews.

Layout
------
  [Author row]  post author name + icon
  [Title]       optional headline (Bilibili title, Instagram username, …)
  [Description] post caption, auto-truncated
  [Image]       first photo or video thumbnail
  [Footer]      platform name + Niibot avatar (via EmbedFactory)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import discord

from core import EmbedFactory

from .constants import (
    BILIBILI_SPACE_URL,
    COLOR_BILIBILI,
    COLOR_INSTAGRAM,
    COLOR_THREADS,
    COLOR_TIKTOK,
    COLOR_TWITCH,
    DESCRIPTION_LIMIT,
    INSTAGRAM_ICON_URL,
)

_TZ_GMT8 = timezone(timedelta(hours=8))


def _fmt_twitch_dt(iso: str, fmt: str, *, fallback: str = "") -> str:
    """Parse a Twitch UTC ISO timestamp and return a GMT+8 formatted string."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(_TZ_GMT8).strftime(fmt)
    except ValueError:
        return fallback


def _fmt_count(n: int) -> str:
    """Format a large integer as a compact human-readable string (e.g. 46200 → '46.2K')."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    for sep in ("\n\n", "\n", " "):
        cut = text.rfind(sep, 0, limit)
        if cut > limit // 2:
            return text[:cut].rstrip() + "…"
    return text[: limit - 1] + "…"


def _strip_trailing_hashtags(text: str) -> str:
    lines = text.splitlines()
    while lines:
        tokens = lines[-1].strip().split()
        if tokens and all(t.startswith("#") for t in tokens):
            lines.pop()
        else:
            break
    return "\n".join(lines).rstrip()


def _extract_author(raw_title: str, suffix: str, *, fallback: str | None = None) -> str | None:
    """Strip a platform suffix from an OG title. e.g. "Alice on Instagram: 'hi'" → "Alice"."""
    if suffix in raw_title:
        return raw_title.split(suffix)[0]
    return fallback


# ── Unified template ──────────────────────────────────────────────────────────


def build_social_embed(
    factory: EmbedFactory,
    *,
    platform: str,
    color: int,
    url: str,
    title: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    author_url: str | None = None,
    description: str | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
    use_platform_footer: bool = True,
) -> discord.Embed:
    """Unified embed template used by every platform handler.

    Pass use_platform_footer=False when the platform is already shown in the
    author row (e.g. Instagram, which uses the Instagram icon as author).
    """
    author = (
        {"name": author_name, "icon_url": author_icon_url, "url": author_url}
        if author_name
        else None
    )
    footer_kwargs: dict[str, Any] = {"footer": platform} if use_platform_footer else {}
    return factory.build(  # type: ignore[no-any-return]
        title=_truncate(title, 256) if title else None,
        description=_truncate(description, DESCRIPTION_LIMIT) if description else None,
        color=discord.Color(color),
        url=url,
        author=author,
        image=image_url,
        thumbnail=thumbnail_url,
        **footer_kwargs,
    )


# ── Platform builders ─────────────────────────────────────────────────────────


def build_instagram_embed(
    factory: EmbedFactory,
    og: dict[str, str],
    post_url: str,
) -> discord.Embed:
    raw_title = og.get("title", "")
    if " on Instagram" in raw_title:
        username = _extract_author(raw_title, " on Instagram")
    else:
        # InstaFix newer format: title is just "@handle" or "handle"
        username = raw_title or None
    description = _strip_trailing_hashtags(og.get("description", ""))

    handle = username.lstrip("@") if username else None
    # Display names from Instagram OG (reels) may be non-ASCII; only use as URL path if ASCII-safe
    profile_url = (
        f"https://www.instagram.com/{handle}/" if handle and handle.isascii() else post_url
    )

    return build_social_embed(
        factory,
        platform="Instagram",
        color=COLOR_INSTAGRAM,
        url=profile_url,
        author_name="Instagram",
        author_icon_url=INSTAGRAM_ICON_URL,
        author_url=post_url,
        title=username,
        description=description or None,
        image_url=og.get("image"),
        use_platform_footer=False,
    )


def build_instagram_profile_embed(
    factory: EmbedFactory,
    og: dict[str, str],
    username: str,
    profile_url: str,
    *,
    posts: int | None = None,
    followers: int | None = None,
    following: int | None = None,
) -> discord.Embed:
    raw_title = og.get("title", "")
    # OG title formats: "Display Name (@handle) • Instagram…" or just "Display Name" / "@handle"
    display_name: str | None = None
    if "•" in raw_title:
        part = raw_title.split("•")[0].strip()
        if part.endswith(")") and " (@" in part:
            part = part.rsplit(" (@", 1)[0].strip()
        display_name = part or None
    elif raw_title:
        display_name = raw_title

    embed = build_social_embed(
        factory,
        platform="Instagram",
        color=COLOR_INSTAGRAM,
        url=profile_url,
        author_name="Instagram",
        author_icon_url=INSTAGRAM_ICON_URL,
        author_url=profile_url,
        title=display_name or f"@{username}",
        description=og.get("description") or None,
        image_url=og.get("image") or None,
        use_platform_footer=False,
    )

    if posts is not None:
        embed.add_field(name="Posts", value=_fmt_count(posts), inline=True)
    if followers is not None:
        embed.add_field(name="Followers", value=_fmt_count(followers), inline=True)
    if following is not None:
        embed.add_field(name="Following", value=_fmt_count(following), inline=True)

    return embed


def build_threads_embed(factory: EmbedFactory, og: dict[str, str], post_url: str) -> discord.Embed:
    raw_title = og.get("title", "")
    description = og.get("description", "")
    author_name = _extract_author(raw_title, " on Threads", fallback=raw_title or None)

    return build_social_embed(
        factory,
        platform="Threads",
        color=COLOR_THREADS,
        url=post_url,
        author_name=author_name,
        description=description or None,
        image_url=og.get("image"),
    )


def build_bilibili_embed(factory: EmbedFactory, data: dict, video_url: str) -> discord.Embed:
    owner = data.get("owner") or {}
    stat = data.get("stat") or {}
    title = data.get("title") or None
    desc = data.get("desc") or ""
    description = desc if desc and desc != title else None

    mid = owner.get("mid")
    author_url = BILIBILI_SPACE_URL.format(mid=mid) if mid else None

    embed = build_social_embed(
        factory,
        platform="Bilibili",
        color=COLOR_BILIBILI,
        url=video_url,
        title=title,
        author_name=owner.get("name") or None,
        author_icon_url=owner.get("face") or None,
        author_url=author_url,
        description=description,
        image_url=data.get("pic") or None,
        use_platform_footer=False,
    )

    view_share = [
        (label, val)
        for label, val in (
            ("播放", stat.get("view") or 0),
            ("分享", stat.get("share") or 0),
        )
        if val
    ]
    for label, val in view_share:
        embed.add_field(name=label, value=_fmt_count(val), inline=True)
    if len(view_share) == 2:
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    for label, val in (
        ("點讚", stat.get("like") or 0),
        ("投幣", stat.get("coin") or 0),
        ("收藏", stat.get("favorite") or 0),
    ):
        if val:
            embed.add_field(name=label, value=_fmt_count(val), inline=True)

    return embed


def build_bilibili_space_embed(factory: EmbedFactory, data: dict, space_url: str) -> discord.Embed:
    card = data.get("card") or {}
    embed = build_social_embed(
        factory,
        platform="Bilibili",
        color=COLOR_BILIBILI,
        url=space_url,
        author_name=card.get("name") or None,
        author_icon_url=card.get("face") or None,
        author_url=space_url,
        description=card.get("sign") or None,
        use_platform_footer=False,
    )

    for label, val in (
        ("影片", data.get("archive_count") or 0),
        ("粉絲", card.get("fans") or 0),
        ("關注", card.get("attention") or 0),
    ):
        if val:
            embed.add_field(name=label, value=_fmt_count(val), inline=True)

    return embed


def build_tiktok_embed(factory: EmbedFactory, oembed: dict, post_url: str) -> discord.Embed:
    return build_social_embed(
        factory,
        platform="TikTok",
        color=COLOR_TIKTOK,
        url=post_url,
        title=oembed.get("title") or None,
        author_name=oembed.get("author_name") or None,
        author_url=oembed.get("author_url") or None,
        image_url=oembed.get("thumbnail_url") or None,
    )


def build_twitch_channel_embed(
    factory: EmbedFactory,
    stream: dict | None,
    user: dict,
    channel_url: str,
) -> discord.Embed:
    """Embed for a Twitch channel page — live or offline."""
    raw_name = user.get("display_name") or user.get("login", "")
    broadcaster_type = user.get("broadcaster_type", "")
    display_name = f"{raw_name}  ✔" if broadcaster_type == "partner" else raw_name
    avatar = user.get("profile_image_url") or None

    if stream:
        thumb = (
            (stream.get("thumbnail_url") or "")
            .replace("{width}", "1280")
            .replace("{height}", "720")
        )
        embed = build_social_embed(
            factory,
            platform="Twitch",
            color=COLOR_TWITCH,
            url=channel_url,
            title=stream.get("title") or None,
            author_name=display_name,
            author_icon_url=avatar,
            author_url=channel_url,
            image_url=thumb or None,
            use_platform_footer=False,
        )
        game = stream.get("game_name") or None
        viewers = stream.get("viewer_count")
        started_at = stream.get("started_at", "")
        start_time = _fmt_twitch_dt(started_at, "%H:%M") if started_at else None

        if game:
            embed.add_field(name="遊戲分類", value=game, inline=True)
        if start_time:
            embed.add_field(name="開播時間", value=start_time, inline=True)
        if viewers is not None:
            embed.add_field(name="觀看人數", value=_fmt_count(viewers), inline=True)
    else:
        bio = user.get("description") or None
        offline_image = user.get("offline_image_url") or None
        embed = build_social_embed(
            factory,
            platform="Twitch",
            color=COLOR_TWITCH,
            url=channel_url,
            author_name=display_name,
            author_icon_url=avatar,
            author_url=channel_url,
            description=bio,
            image_url=offline_image,
            use_platform_footer=False,
        )

    return embed


def build_twitch_clip_embed(
    factory: EmbedFactory,
    data: dict,
    clip_url: str,
    *,
    broadcaster_avatar: str | None = None,
    broadcaster_url: str | None = None,
    game_name: str | None = None,
) -> discord.Embed:
    duration = data.get("duration", 0)
    minutes, seconds = divmod(int(duration), 60)

    embed = build_social_embed(
        factory,
        platform="Twitch",
        color=COLOR_TWITCH,
        url=clip_url,
        title=data.get("title") or None,
        author_name=data.get("broadcaster_name") or None,
        author_icon_url=broadcaster_avatar,
        author_url=broadcaster_url,
        image_url=data.get("thumbnail_url") or None,
        use_platform_footer=False,
    )

    # Row 1: category | duration | clip date
    if game_name:
        embed.add_field(name="遊戲分類", value=game_name, inline=True)
    embed.add_field(name="片段時長", value=f"{minutes:02d}:{seconds:02d}", inline=True)
    created_at = data.get("created_at", "")
    if created_at:
        embed.add_field(name="剪輯時間", value=_fmt_twitch_dt(created_at, "%Y-%m-%d"), inline=True)

    # Row 2: creator | views | spacer
    creator = data.get("creator_name")
    if creator:
        embed.add_field(name="剪輯作者", value=creator, inline=True)
    views = data.get("view_count")
    if views:
        embed.add_field(name="觀看次數", value=_fmt_count(views), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    return embed
