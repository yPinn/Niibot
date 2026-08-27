"""Interactive reply views for the social-preview cog.

A dismiss-on-timeout base plus ◀ 1/N ▶ carousel navigation for Instagram
and Threads multi-image posts. All rendering is delegated back to the
``_embeds`` builders; these classes only own button state and navigation.
"""

from __future__ import annotations

import discord

from core import EmbedFactory, UserBoundView

from ._embeds import build_instagram_embed, build_threads_embed
from .constants import DISMISS_TIMEOUT


class _BasePreviewView(UserBoundView):
    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass


class _CarouselView(_BasePreviewView):
    """Base class for ◀ 1/N ▶ carousel navigation views."""

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
    ) -> None:
        super().__init__(user_id, timeout=DISMISS_TIMEOUT)
        self._items = items
        self.current = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self._items) - 1
        self.page_btn.label = f"{self.current + 1}/{len(self._items)}"

    def _build_embed(self) -> discord.Embed:
        raise NotImplementedError

    async def _navigate(self, interaction: discord.Interaction) -> None:
        # Guard against Discord race condition where a disabled button fires late.
        if not (0 <= self.current < len(self._items)):
            await interaction.response.defer()
            return
        await interaction.response.edit_message(
            embed=self._build_embed(), view=self, attachments=[]
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current = max(0, self.current - 1)
        self._sync_buttons()
        await self._navigate(interaction)

    @discord.ui.button(label="…", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.current = min(len(self._items) - 1, self.current + 1)
        self._sync_buttons()
        await self._navigate(interaction)

    async def on_timeout(self) -> None:
        if self.message:
            try:
                self.current = 0
                await self.message.edit(embed=self._build_embed(), view=None, attachments=[])
            except (discord.NotFound, discord.HTTPException):
                pass


class _InstagramCarouselView(_CarouselView):
    """◀ 1/N ▶ photo navigation for Instagram carousel posts."""

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
        factory: EmbedFactory,
        og_meta: dict[str, str],
        post_url: str,
    ) -> None:
        super().__init__(user_id, items)
        self._factory = factory
        self._og_meta = og_meta
        self._post_url = post_url

    def _build_embed(self) -> discord.Embed:
        image_cdn, _ = self._items[self.current]
        meta = {**self._og_meta, "image": image_cdn} if image_cdn else self._og_meta
        return build_instagram_embed(self._factory, meta, self._post_url)


class _ThreadsCarouselView(_CarouselView):
    """◀ 1/N ▶ navigation for Threads image carousel posts.

    Paginates image slots only. Videos are sent once as a bundled reply at
    creation time and are never deleted by this view.
    """

    def __init__(
        self,
        user_id: int,
        items: list[tuple[str | None, str | None]],
        factory: EmbedFactory,
        data: dict,
        post_url: str,
    ) -> None:
        super().__init__(user_id, items)
        self._factory = factory
        self._data = data
        self._post_url = post_url

    def _build_embed(self) -> discord.Embed:
        image_url, _ = self._items[self.current]
        return build_threads_embed(
            self._factory,
            {**self._data, "image_urls": [image_url] if image_url else [], "video_urls": []},
            self._post_url,
        )
