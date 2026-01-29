"""Eat feature module."""

from .cog import EatCog

__all__ = ["EatCog", "setup"]


async def setup(bot):
    """Extension entry point."""
    cog = EatCog(bot)

    # Autocomplete setup
    cog.eat_command.autocomplete("category")(cog._category_autocomplete)
    cog.food_show.autocomplete("category")(cog._category_autocomplete)
    cog.food_add.autocomplete("category")(cog._category_autocomplete)
    cog.food_remove.autocomplete("category")(cog._category_autocomplete)
    cog.food_remove.autocomplete("item")(cog._item_autocomplete)
    cog.food_delete.autocomplete("category")(cog._category_autocomplete)

    await bot.add_cog(cog)
