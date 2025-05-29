import discord
from discord.ext import commands
from utils.util import format_error_msg, format_success_msg, Cooldown


class Clear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown = Cooldown(10)  # 10秒冷卻防濫用

    @commands.command(name="clear", help="刪除上方包含 bot 訊息在內的 X 則使用者訊息區塊（預設 100）")
    @commands.has_permissions(manage_messages=True)
    async def clear_all_messages(self, ctx: commands.Context, amount: int = 100):
        user_id = ctx.author.id

        if self.cooldown.is_on_cooldown(user_id):
            await ctx.send(format_error_msg("請稍等，指令冷卻中。"))
            return

        if amount < 1:
            await ctx.send(format_error_msg("請輸入正確的數量（大於 0）。"))
            return

        try:
            await ctx.message.delete()  # 刪除指令本身

            def is_user_message(m: discord.Message):
                return not m.author.bot

            messages_to_delete = []
            user_message_count = 0

            async for msg in ctx.channel.history(limit=1000, oldest_first=False):
                if msg.id == ctx.message.id:
                    continue  # 跳過指令訊息

                messages_to_delete.append(msg)

                if is_user_message(msg):
                    user_message_count += 1

                if user_message_count >= amount:
                    break

            if not messages_to_delete:
                await ctx.send(format_error_msg("找不到可刪除的訊息。"))
                return

            # 分開刪除
            deleted_count = 0
            if len(messages_to_delete) == 1:
                try:
                    await messages_to_delete[0].delete()
                    if is_user_message(messages_to_delete[0]):
                        deleted_count = 1
                except:
                    pass
            else:
                deleted = await ctx.channel.delete_messages(messages_to_delete)
                if deleted is not None:
                    deleted_count = sum(
                        1 for m in deleted if is_user_message(m))

            confirm = await ctx.send(format_success_msg(f"已刪除 {amount} 則使用者訊息（共 {len(messages_to_delete)} 則訊息被清除）。"))
            await confirm.delete(delay=2)

            self.cooldown.update_timestamp(user_id)

        except Exception as e:
            try:
                await ctx.send(format_error_msg(f"發生錯誤：{str(e)}"))
            except discord.NotFound:
                pass

    @clear_all_messages.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(format_error_msg("你沒有管理訊息的權限，無法執行此指令。"))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(format_error_msg("參數錯誤，請輸入數字，例如：`?clear 50`。"))


async def setup(bot):
    await bot.add_cog(Clear(bot))
