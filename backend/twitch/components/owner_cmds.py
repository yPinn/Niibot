from typing import TYPE_CHECKING

from twitchio.ext import commands

if TYPE_CHECKING:
    from main import Bot
else:
    from twitchio.ext.commands import Bot


class NotOwnerError(commands.GuardFailure):
    """Custom exception for owner-only command guard."""

    ...


class OwnerCmds(commands.Component):
    """Owner-only commands for bot management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def component_command_error(self, payload: commands.CommandErrorPayload) -> bool | None:
        """Handle component-specific errors."""
        error = payload.exception
        if isinstance(error, NotOwnerError):
            ctx = payload.context
            await ctx.reply("Only the owner can use this command!")
            return False
        return None

    @commands.Component.guard()
    def is_owner(self, ctx: commands.Context[Bot]) -> bool:
        """Restrict all commands in this component to the owner.

        Owner is defined by OWNER_ID in .env file.
        Owner does NOT need to authorize via OAuth to use these commands.
        Owner CAN also be a broadcaster (by authorizing via OAuth separately).
        """
        if ctx.chatter.id != self.bot.owner_id:
            raise NotOwnerError
        return True

    @commands.command()
    async def load(self, ctx: commands.Context[Bot], module: str) -> None:
        """Load a module dynamically.

        Usage: !load <module_name>
        Example: !load components.cmds
        """
        try:
            await self.bot.load_module(module)
            await ctx.reply(f"Loaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to load {module}: {str(e)}")

    @commands.command()
    async def unload(self, ctx: commands.Context[Bot], module: str) -> None:
        """Unload a module dynamically.

        Usage: !unload <module_name>
        Example: !unload components.cmds
        """
        if module == "components.owner_cmds":
            await ctx.reply("Cannot unload owner_cmds (would lose bot control)")
            return

        try:
            await self.bot.unload_module(module)
            await ctx.reply(f"Unloaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to unload {module}: {str(e)}")

    @commands.command()
    async def reload(self, ctx: commands.Context[Bot], module: str) -> None:
        """Hot reload a module atomically.

        Usage: !reload <module_name>
        Example: !reload components.cmds
        """
        try:
            await self.bot.reload_module(module)
            await ctx.reply(f"Reloaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to reload {module}: {str(e)}")

    @commands.command(aliases=["modules", "mods"])
    async def loaded(self, ctx: commands.Context[Bot]) -> None:
        """List all currently loaded modules.

        Usage: !loaded, !modules, !mods
        """
        modules = list(self.bot.modules.keys())
        if modules:
            modules_str = ", ".join(modules)
            await ctx.reply(f"Loaded ({len(modules)}): {modules_str}")
        else:
            await ctx.reply("No modules loaded.")

    @commands.command()
    async def shutdown(self, ctx: commands.Context[Bot]) -> None:
        """Gracefully shutdown the bot.

        Usage: !shutdown
        """
        await ctx.reply("Shutting down bot...")
        await self.bot.close()


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(OwnerCmds(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
