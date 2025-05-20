import datetime

import discord
from discord.ext import commands
from discord.ui import Button, View


class ViewClass(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❌",
                       style=discord.ButtonStyle.secondary,
                       custom_id="nope_button")
    async def nope(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("You clicked ❌ Nope",
                                                ephemeral=True)

    @discord.ui.button(label="💚",
                       style=discord.ButtonStyle.primary,
                       custom_id="like_button")
    async def like(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("You clicked 💚 Like",
                                                ephemeral=True)


class Tinder(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data = {}

    @commands.command()
    async def status(self, ctx: commands.Context):
        uid = str(ctx.author.id)
        if uid in self.user_data:
            await ctx.send("You have data stored.")
        else:
            await ctx.send("No data found.")

    @commands.command(name="t")
    async def tinder(self, ctx: commands.Context):
        user = ctx.author
        avatar = user.display_avatar.url
        username = user.display_name
        activity = user.activity.name
        wrap_activity = self.wrap_text(activity, 20)
        bot_avatar = self.bot.user.display_avatar.url

        embed = discord.Embed(title=f"{username}",
                              description=f" _{wrap_activity}_ ",
                              colour=0xff6b6b,
                              timestamp=datetime.datetime.now())

        embed.set_author(
            name="Tinder",
            icon_url="https://tinder.com/static/android-chrome-192x192.png")

        embed.set_image(url=avatar)

        embed.set_footer(text="Niibot", icon_url=bot_avatar)

        view = ViewClass()
        await ctx.send(embed=embed, view=view)

    def wrap_text(self, text: str, line_length: int) -> str:
        return '\n'.join([
            text[i:i + line_length] for i in range(0, len(text), line_length)
        ])


async def setup(bot: commands.Bot):
    await bot.add_cog(Tinder(bot))
