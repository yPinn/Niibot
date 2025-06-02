from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from utils.util import Cooldown, format_error_msg, format_success_msg


class Clear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown = Cooldown(10)  # 10 秒冷卻

    @commands.command(
        name="clear",
        help="刪除上方包含 bot 訊息在內的 X 則使用者訊息區塊（預設 100）"
    )
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
            try:
                await ctx.message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                print(format_error_msg(f"刪除指令訊息失敗：{e}"))

            def is_user_message(m: discord.Message):
                return not m.author.bot

            messages_to_delete = []
            user_msg_count = 0

            async for msg in ctx.channel.history(limit=1000, oldest_first=False):
                if msg.id == ctx.message.id:
                    continue
                messages_to_delete.append(msg)
                if is_user_message(msg):
                    user_msg_count += 1
                if user_msg_count >= amount:
                    break

            if not messages_to_delete:
                await ctx.send(format_error_msg("找不到可刪除的訊息。"))
                return

            cutoff = datetime.now(timezone.utc) - timedelta(days=14)
            deletable_messages = [
                m for m in messages_to_delete if m.created_at > cutoff]

            deleted_count = 0
            user_deleted_count = 0

            try:
                if len(deletable_messages) == 1:
                    await deletable_messages[0].delete()
                    deleted_count = 1
                    if is_user_message(deletable_messages[0]):
                        user_deleted_count = 1
                else:
                    deleted = await ctx.channel.delete_messages(deletable_messages)
                    if deleted is not None:
                        deleted_count = len(deleted)
                        user_deleted_count = sum(
                            1 for m in deleted if is_user_message(m))
                    else:
                        deleted_count = len(deletable_messages)
                        user_deleted_count = sum(
                            1 for m in deletable_messages if is_user_message(m))
            except discord.HTTPException as e:
                await ctx.send(format_error_msg(f"刪除訊息失敗：{e}"))
                return

            try:
                confirm = await ctx.send(format_success_msg(
                    f"已刪除 {user_deleted_count} 則使用者訊息（總共清除 {deleted_count} 則訊息）"
                ))
                await confirm.delete(delay=2)
            except discord.HTTPException as e:
                print(format_error_msg(f"無法發送或刪除確認訊息：{e}"))

            self.cooldown.update_timestamp(user_id)

        except Exception as e:
            try:
                await ctx.send(format_error_msg(f"發生錯誤：{str(e)}"))
            except discord.NotFound:
                pass

    @clear_all_messages.error
    async def clear_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(format_error_msg("你沒有管理訊息的權限，無法執行此指令。"))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(format_error_msg("參數錯誤，請輸入數字，例如：`?clear 50`。"))
        else:
            await ctx.send(format_error_msg(f"發生錯誤：{error}"))


async def setup(bot):
    await bot.add_cog(Clear(bot))
