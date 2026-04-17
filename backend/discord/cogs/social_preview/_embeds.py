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

from typing import Any

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
        embed.add_field(name="Posts", value=f"{posts:,}", inline=True)
    if followers is not None:
        embed.add_field(name="Followers", value=_fmt_count(followers), inline=True)
    if following is not None:
        embed.add_field(name="Following", value=f"{following:,}", inline=True)

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
