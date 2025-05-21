from discord.ext import commands


class Clear(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear_all_messages(self, ctx: commands.Context):
        deleted = await ctx.channel.purge(limit=None)
        await ctx.send(f"✅ 已清除 {len(deleted)} 則訊息", delete_after=3)

    @clear_all_messages.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 你沒有權限使用這個指令！")
        else:
            await ctx.send(f"⚠️ 發生錯誤：{str(error)}")


async def setup(bot):
    await bot.add_cog(Clear(bot))
