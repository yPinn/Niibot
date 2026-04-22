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

import re
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
    THREADS_ICON_URL,
)

_TZ_GMT8 = timezone(timedelta(hours=8))


def _fmt_dt(
    raw: str,
    out_fmt: str,
    *,
    utc_to_gmt8: bool = False,
    skip_prefix: str | None = None,
) -> str | None:
    """Parse a datetime string and return a formatted string, or None on failure.

    Handles both UTC ISO 8601 (Twitch: "2024-03-15T10:00:00Z") and Bilibili's
    native "YYYY-MM-DD HH:MM:SS" format (already CST/UTC+8) — fromisoformat
    accepts both after the "Z" → "+00:00" substitution.

    Args:
        raw:          Input datetime string; empty strings return None.
        out_fmt:      strftime format for the output value.
        utc_to_gmt8:  Convert from UTC → GMT+8 before formatting (Twitch).
                      Leave False when the timestamp is already CST (Bilibili).
        skip_prefix:  Return None immediately if raw starts with this prefix,
                      e.g. "0000" to skip Bilibili's offline sentinel
                      "0000-00-00 00:00:00".
    """
    if not raw or (skip_prefix and raw.startswith(skip_prefix)):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if utc_to_gmt8:
            dt = dt.astimezone(_TZ_GMT8)
        return dt.strftime(out_fmt)
    except ValueError:
        return None


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


# Matches Meta's Discordbot OG title: "DisplayName (@handle)" or "DisplayName (@handle) on Threads"
_THREADS_OG_TITLE_RE = re.compile(r"^(.+?)\s+\(@([\w.]+)\)(?:\s+on\s+Threads)?$", re.IGNORECASE)
# Matches profile OG title: "DisplayName (@handle) • Threads, Say more"
_THREADS_PROFILE_TITLE_RE = re.compile(r"^(.+?)\s+\(@([\w.]+)\)\s*[•·]", re.IGNORECASE)
# Strips Meta's "N Replies. See more…" CTA from the end of a description, preserving any caption that precedes it.
_THREADS_CTA_SUFFIX_RE = re.compile(
    r"\s*\d[\d,.]*[KMB]?\s+\w+\.\s+See more\b.*$", re.IGNORECASE | re.DOTALL
)


def get_threads_handle(data: dict[str, str]) -> str | None:
    """Extract the Threads username from oEmbed or OG scrape data.

    - oEmbed: reads ``author_url`` (e.g. ``https://www.threads.com/@handle``)
    - OG:     parses ``title`` (e.g. ``"DisplayName (@handle) on Threads"``)
    """
    if "author_url" in data:
        m = re.search(r"/@([\w.]+)/?(?:\?.*)?$", data["author_url"])
        return m.group(1) if m else None
    m = _THREADS_OG_TITLE_RE.match(data.get("title", ""))
    return m.group(2) if m else None


def build_threads_embed(
    factory: EmbedFactory,
    data: dict[str, Any],
    post_url: str,
) -> discord.Embed:
    """Build embed from Threads oEmbed data or OG tags.

    Layout mirrors the Instagram pattern:
    - author row: Threads logo + "Threads" → post URL
    - title:       account display (DisplayName (@handle) or oEmbed author_name)
    - description: post caption (CTA suffix stripped)
    - image:       post photo / video thumbnail

    Accepts either:
    - oEmbed dict (``author_name``, ``author_url``, optionally ``thumbnail_url``)
    - OG scrape dict (``title``, ``description``, ``image``) served to Discordbot UA
    """
    # Prefer scrapling media in order: image → video poster → OG fallback.
    image_urls: list[str] = data.get("image_urls") or []
    video_urls: list[str] = data.get("video_urls") or []
    scrapling_image = image_urls[0] if image_urls else (video_urls[0] if video_urls else None)

    if "author_name" in data:
        # oEmbed path — author_name is already the display name
        account = data.get("author_name") or None
        profile_url = data.get("author_url") or post_url
        description: str | None = None
        image_url = scrapling_image or data.get("thumbnail_url") or None
    else:
        # OG path — "DisplayName (@handle)" or "DisplayName (@handle) on Threads"
        raw_title = data.get("title", "")
        m = _THREADS_OG_TITLE_RE.match(raw_title)
        if m:
            display_name, handle = m.group(1), m.group(2)
            account = f"{display_name} (@{handle})"
            profile_url = f"https://www.threads.com/@{handle}"
        else:
            account = _extract_author(raw_title, " on Threads", fallback=raw_title or None)
            profile_url = post_url

        # Prefer explicit caption injected by Scrapling sidecar; otherwise strip
        # Meta's "N Replies. See more…" CTA from og:description, preserving any real caption.
        if explicit := data.get("caption"):
            description = explicit
        else:
            description = (
                _THREADS_CTA_SUFFIX_RE.sub("", data.get("description", "")).strip() or None
            )
        image_url = scrapling_image or data.get("image") or None

    embed = build_social_embed(
        factory,
        platform="Threads",
        color=COLOR_THREADS,
        url=profile_url,
        author_name="Threads",
        author_icon_url=THREADS_ICON_URL,
        author_url=post_url,
        title=account,
        description=description,
        image_url=image_url,
        use_platform_footer=False,
    )

    for key, label in (("like_count", "點讚"), ("reply_count", "留言"), ("share_count", "分享")):
        embed.add_field(name=label, value=data.get(key) or "—", inline=True)

    return embed


def build_threads_profile_embed(
    factory: EmbedFactory,
    data: dict[str, str],
    profile_url: str,
) -> discord.Embed:
    raw_title = data.get("title", "")
    m = _THREADS_PROFILE_TITLE_RE.match(raw_title) or _THREADS_OG_TITLE_RE.match(raw_title)
    title: str | None
    if m:
        display_name, handle = m.group(1), m.group(2)
        title = f"{display_name} (@{handle})"
    else:
        title = raw_title or None

    embed = build_social_embed(
        factory,
        platform="Threads",
        color=COLOR_THREADS,
        url=profile_url,
        author_name="Threads",
        author_icon_url=THREADS_ICON_URL,
        author_url=None,
        title=title,
        description=data.get("bio") or None,
        thumbnail_url=data.get("image") or None,
        use_platform_footer=False,
    )

    if followers := data.get("followers"):
        embed.add_field(name="粉絲", value=followers, inline=True)
    if recent_views := data.get("recent_views"):
        embed.add_field(name="近期瀏覽", value=recent_views, inline=True)

    return embed


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
        start_time = _fmt_dt(stream.get("started_at", ""), "%H:%M", utc_to_gmt8=True)

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


_BILIBILI_LIVE_STATUS: dict[int, str] = {0: "下播", 1: "直播中", 2: "輪播"}


def build_bilibili_live_embed(
    factory: EmbedFactory,
    room: dict,
    card_data: dict | None,
    room_url: str,
) -> discord.Embed:
    """Embed for a Bilibili live room — live, offline, or rotating.

    Field layout (inline grid, 3 per row):
      Live:    狀態 | 分類 | 觀看人數
               開播時間 | 關注 | ​(spacer)
      Offline: 狀態 | 分類 | 關注
    """
    title = room.get("title") or None
    live_status = room.get("live_status", 0)
    status_label = _BILIBILI_LIVE_STATUS.get(live_status, "下播")

    # keyframe = live screenshot (only valid while streaming); fallback to cover
    cover: str | None
    if live_status == 1:
        cover = room.get("keyframe") or room.get("user_cover") or None
    else:
        cover = room.get("user_cover") or None

    card = (card_data or {}).get("card") or {}
    uid = room.get("uid")
    author_url = f"https://space.bilibili.com/{uid}" if uid else None

    embed = build_social_embed(
        factory,
        platform="Bilibili",
        color=COLOR_BILIBILI,
        url=room_url,
        title=title,
        author_name=card.get("name") or None,
        author_icon_url=card.get("face") or None,
        author_url=author_url,
        image_url=cover,
        use_platform_footer=False,
    )

    # ── Row 1 ──────────────────────────────────────────────────────────────────
    embed.add_field(name="狀態", value=status_label, inline=True)
    area = room.get("area_name") or room.get("parent_area_name") or None
    if area:
        embed.add_field(name="分類", value=area, inline=True)
    attention = room.get("attention") or 0
    if live_status == 1:
        online = room.get("online")
        if online is not None:
            embed.add_field(name="觀看人數", value=_fmt_count(online), inline=True)
    else:
        if attention:
            embed.add_field(name="關注", value=_fmt_count(attention), inline=True)

    # ── Row 2 (live only) ──────────────────────────────────────────────────────
    if live_status == 1:
        row2: list[tuple[str, str]] = []
        start_time = _fmt_dt(room.get("live_time", ""), "%H:%M", skip_prefix="0000")
        if start_time:
            row2.append(("開播時間", start_time))
        if attention:
            row2.append(("關注", _fmt_count(attention)))
        for name, value in row2:
            embed.add_field(name=name, value=value, inline=True)
        if len(row2) == 2:
            embed.add_field(name="\u200b", value="\u200b", inline=True)

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
    if clip_date := _fmt_dt(data.get("created_at", ""), "%Y-%m-%d", utc_to_gmt8=True):
        embed.add_field(name="剪輯時間", value=clip_date, inline=True)

    # Row 2: creator | views | spacer
    creator = data.get("creator_name")
    if creator:
        embed.add_field(name="剪輯作者", value=creator, inline=True)
    views = data.get("view_count")
    if views:
        embed.add_field(name="觀看次數", value=_fmt_count(views), inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)

    return embed
