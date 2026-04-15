"""Shared embed factory for all Discord cogs."""

from __future__ import annotations

from datetime import datetime

import discord

# Sentinel: "use the value from global embed.json config"
_UNSET = object()


class EmbedFactory:
    """Build discord.Embed with global chrome (author + footer) auto-applied.

    Initialise once per cog::

        self._embed = EmbedFactory(load_json(DATA_DIR / "embed.json"))

    Build embeds with named props — author and footer come from config by
    default; pass explicit values to override or suppress::

        embed = self._embed.build(
            title="AI 回應",
            color=discord.Color.blue(),
            thumbnail=user.avatar.url,
        )
        embed.add_field(...)

    Override chrome for special cases::

        embed = self._embed.build(
            title="Custom",
            author={"name": "Someone", "icon_url": "..."},  # override
            footer="數據來源: tactics.tools",                 # custom text
        )

    Suppress chrome entirely::

        embed = self._embed.build(title="Log", author=None, footer=None)
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg = cfg

    # ------------------------------------------------------------------

    def build(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        color: discord.Color = discord.Color.default(),
        url: str | None = None,
        timestamp: datetime | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
        # author: _UNSET → cfg, None → skip, dict → custom
        author: dict | None | object = _UNSET,
        # footer: _UNSET → cfg text+icon
        #         None   → skip
        #         str    → custom text, still inherits cfg icon for branding
        footer: str | None | object = _UNSET,
        footer_icon: str | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            url=url,
        )
        if timestamp is not None:
            embed.timestamp = timestamp

        # ── Author ────────────────────────────────────────────────────
        _a: dict = (
            self._cfg.get("author", {}) if author is _UNSET else {} if author is None else author  # type: ignore[assignment]
        )
        if isinstance(_a, dict) and _a.get("name"):
            embed.set_author(
                name=_a["name"],
                icon_url=_a.get("icon_url"),
                url=_a.get("url"),
            )

        # ── Footer ────────────────────────────────────────────────────
        _cfg_footer = self._cfg.get("footer", {})

        if footer is _UNSET:
            _ft: str | None = _cfg_footer.get("text")
            _fi: str | None = footer_icon or _cfg_footer.get("icon_url")
        elif footer is None:
            _ft, _fi = None, None
        else:
            _ft = str(footer)
            # Custom text still inherits cfg icon for branding consistency
            _fi = footer_icon or _cfg_footer.get("icon_url")

        if _ft:
            embed.set_footer(text=_ft, icon_url=_fi)

        # ── Media ─────────────────────────────────────────────────────
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)

        return embed
