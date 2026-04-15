"""Shared base views for Discord cogs."""

from __future__ import annotations

import discord


class UserBoundView(discord.ui.View):
    """View that restricts interactions to the user who triggered it.

    - ``interaction_check`` rejects non-owners with an ephemeral message.
    - ``on_timeout`` disables all children and edits the stored message.

    Usage::

        class MyView(UserBoundView):
            def __init__(self, user_id: int) -> None:
                super().__init__(user_id, timeout=180)
            ...

        view = MyView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    """

    def __init__(self, user_id: int, *, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass
