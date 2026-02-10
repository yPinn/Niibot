from typing import TYPE_CHECKING

from twitchio.ext import commands

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


class NotOwnerError(commands.GuardFailure):
    """Custom exception for owner-only command guard."""

    ...


class OwnerCmds(commands.Component):
    """Owner-only commands for bot management.

    Usage:
        !comp          List loaded modules
        !comp l <mod>  Load a module
        !comp u <mod>  Unload a module
        !comp r <mod>  Reload a module
        !comp off      Shutdown the bot
    """

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
        """Restrict all commands in this component to the owner."""
        if ctx.chatter.id != self.bot.owner_id:
            raise NotOwnerError
        return True

    @commands.group(name="comp")
    async def comp(self, ctx: commands.Context[Bot]) -> None:
        """Component management group. Lists loaded modules by default."""
        if ctx.invoked_subcommand is None:
            modules = list(self.bot.modules.keys())
            if modules:
                modules_str = ", ".join(modules)
                await ctx.reply(f"Loaded ({len(modules)}): {modules_str}")
            else:
                await ctx.reply("No modules loaded.")

    @comp.command(name="l")
    async def comp_load(self, ctx: commands.Context[Bot], module: str) -> None:
        """Load a module dynamically.

        Usage: !comp l <module_name>
        Example: !comp l components.cmds
        """
        try:
            await self.bot.load_module(module)
            await ctx.reply(f"Loaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to load {module}: {str(e)}")

    @comp.command(name="u")
    async def comp_unload(self, ctx: commands.Context[Bot], module: str) -> None:
        """Unload a module dynamically.

        Usage: !comp u <module_name>
        Example: !comp u components.cmds
        """
        if module == "components.owner_cmds":
            await ctx.reply("Cannot unload owner_cmds (would lose bot control)")
            return

        try:
            await self.bot.unload_module(module)
            await ctx.reply(f"Unloaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to unload {module}: {str(e)}")

    @comp.command(name="r")
    async def comp_reload(self, ctx: commands.Context[Bot], module: str) -> None:
        """Hot reload a module atomically.

        Usage: !comp r <module_name>
        Example: !comp r components.cmds
        """
        try:
            await self.bot.reload_module(module)
            await ctx.reply(f"Reloaded: {module}")
        except Exception as e:
            await ctx.reply(f"Failed to reload {module}: {str(e)}")

    @comp.command(name="off")
    async def comp_off(self, ctx: commands.Context[Bot]) -> None:
        """Gracefully shutdown the bot.

        Usage: !comp off
        """
        await ctx.reply("Shutting down bot...")
        await self.bot.close()


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(OwnerCmds(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
