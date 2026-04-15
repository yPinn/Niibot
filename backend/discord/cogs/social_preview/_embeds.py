"""Unified embed builder for social media previews.

All platforms share the same visual structure so the output is
consistent regardless of which platform generated it.

Layout
------
  [Author row]  name (+ small avatar)
  [Title]       optional — used for content with a distinct headline
                (Bilibili video title, …)
  [Description] post body / caption, auto-truncated
  [Image]       first photo or video thumbnail
  [Footer]      platform name
"""

from __future__ import annotations

import discord

from .constants import (
    COLOR_BILIBILI,
    COLOR_INSTAGRAM,
    COLOR_THREADS,
    COLOR_TIKTOK,
    DESCRIPTION_LIMIT,
)


def _truncate(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# ── Unified template ──────────────────────────────────────────────────────────


def build_social_embed(
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
) -> discord.Embed:
    """Unified embed template used by every platform handler."""
    embed = discord.Embed(
        title=_truncate(title, 256) if title else None,
        description=_truncate(description) if description else None,
        color=color,
        url=url,
    )
    if author_name:
        embed.set_author(
            name=author_name,
            icon_url=author_icon_url,
            url=author_url,
        )
    if image_url:
        embed.set_image(url=image_url)

    embed.set_footer(text=platform)
    return embed


# ── Platform builders ─────────────────────────────────────────────────────────


def build_instagram_embed(og: dict[str, str], post_url: str) -> discord.Embed:
    """Build embed from InstaFix (ddinstagram) OG data."""
    raw_title = og.get("title", "")
    description = og.get("description", "")

    author_name = raw_title.split(" on Instagram")[0] if " on Instagram" in raw_title else None

    return build_social_embed(
        platform="Instagram",
        color=COLOR_INSTAGRAM,
        url=post_url,
        author_name=author_name,
        description=description or raw_title or None,
        image_url=og.get("image"),
    )


def build_threads_embed(og: dict[str, str], post_url: str) -> discord.Embed:
    raw_title = og.get("title", "")
    description = og.get("description", "")

    author_name = (
        raw_title.split(" on Threads")[0] if " on Threads" in raw_title else raw_title or None
    )

    return build_social_embed(
        platform="Threads",
        color=COLOR_THREADS,
        url=post_url,
        author_name=author_name,
        description=description or None,
        image_url=og.get("image"),
    )


def build_bilibili_embed(data: dict, video_url: str) -> discord.Embed:
    """Build embed from Bilibili API response data dict."""
    owner = data.get("owner") or {}
    stat = data.get("stat") or {}
    title = data.get("title") or None
    desc = data.get("desc") or ""
    description = desc if desc and desc != title else None

    embed = build_social_embed(
        platform="Bilibili",
        color=COLOR_BILIBILI,
        url=video_url,
        title=title,
        author_name=owner.get("name") or None,
        author_icon_url=owner.get("face") or None,
        description=description,
        image_url=data.get("pic") or None,
    )

    metrics: list[str] = []
    if stat.get("view"):
        metrics.append(f"▶ {stat['view']:,}")
    if stat.get("like"):
        metrics.append(f"👍 {stat['like']:,}")
    if stat.get("coin"):
        metrics.append(f"🪙 {stat['coin']:,}")
    if stat.get("favorite"):
        metrics.append(f"⭐ {stat['favorite']:,}")
    if metrics:
        embed.add_field(name="", value="  ".join(metrics), inline=False)

    return embed


def build_tiktok_embed(oembed: dict, post_url: str) -> discord.Embed:
    """Build embed from TikTok oEmbed API response."""
    return build_social_embed(
        platform="TikTok",
        color=COLOR_TIKTOK,
        url=post_url,
        title=oembed.get("title") or None,
        author_name=oembed.get("author_name") or None,
        author_url=oembed.get("author_url") or None,
        image_url=oembed.get("thumbnail_url") or None,
    )
