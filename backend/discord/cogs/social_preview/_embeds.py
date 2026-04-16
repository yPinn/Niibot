"""Unified embed builder for social media previews.

All platforms share the same visual structure so the output is
consistent regardless of which platform generated it.

Layout
------
  [Author row]  post author name (+ icon if available)
  [Title]       optional — used for content with a distinct headline
                (Bilibili video title, …)
  [Description] post body / caption, auto-truncated
  [Image]       first photo or video thumbnail
  [Footer]      platform name  +  Niibot avatar icon (via EmbedFactory)
"""

from __future__ import annotations

import discord

from core import EmbedFactory

from .constants import (
    COLOR_BILIBILI,
    COLOR_INSTAGRAM,
    COLOR_THREADS,
    COLOR_TIKTOK,
    DESCRIPTION_LIMIT,
    INSTAGRAM_ICON_URL,
)


def _truncate(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _extract_author(raw_title: str, suffix: str, *, fallback: str | None = None) -> str | None:
    """Strip a platform suffix from an OG title to get the author name.

    e.g. "Alice on Instagram: 'hi'" → "Alice"
    Falls back to *fallback* when the suffix is absent.
    """
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

    Uses EmbedFactory so the footer inherits the global Niibot avatar icon
    while the footer text shows the originating platform name.
    Pass *use_platform_footer=False* to fall back to the Niibot config footer
    (useful when the platform is already shown in the author row).
    """
    author = (
        {"name": author_name, "icon_url": author_icon_url, "url": author_url}
        if author_name
        else None
    )
    footer_kwargs: dict = {} if not use_platform_footer else {"footer": platform}
    return factory.build(
        title=_truncate(title, 256) if title else None,
        description=_truncate(description) if description else None,
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
    description = og.get("description", "")

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

    embed = build_social_embed(
        factory,
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
