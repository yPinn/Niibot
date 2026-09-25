"""Utility commands"""

import sys
from typing import NamedTuple

import discord
from discord import app_commands
from discord.ext import commands

from core import BOT_NAME, BOT_VERSION, GIT_COMMIT, EmbedFactory, UserBoundView


class _Cmd(NamedTuple):
    usage: str
    description: str


class _Category(NamedTuple):
    title: str
    intro: str
    commands: list[_Cmd]


_PUBLIC_CATEGORIES: list[_Category] = [
    _Category(
        "工具",
        "Bot 基本功能與資訊查詢",
        [
            _Cmd("/ping", "查看 Bot 目前的網路延遲"),
            _Cmd("/version", "顯示 Bot 版本與 Git Commit 資訊"),
            _Cmd("/info server", "查看目前伺服器的詳細資訊"),
            _Cmd("/info user [成員]", "查看指定成員的個人資訊"),
            _Cmd("/info avatar [成員]", "查看指定成員的頭像"),
            _Cmd("/help", "顯示此指令說明"),
        ],
    ),
    _Category(
        "遊戲",
        "各種互動小遊戲",
        [
            _Cmd("/game roll [面數]", "擲骰子，預設為 D6"),
            _Cmd("/game choose <選項...>", "從多個選項中隨機選一個"),
            _Cmd("/game rps", "與 Bot 玩猜拳"),
            _Cmd("/game roulette", "俄羅斯輪盤"),
        ],
    ),
    _Category(
        "占卜",
        "運勢與塔羅牌",
        [
            _Cmd("/fortune", "抽取今日綜合運勢"),
            _Cmd("/tarot [主題]", "抽取塔羅牌，可指定主題"),
        ],
    ),
    _Category(
        "AI",
        "AI 問答功能",
        [
            _Cmd("/ai <問題>", "向 AI 提問，以繁體中文回答"),
        ],
    ),
    _Category(
        "餐點",
        "餐點推薦與瀏覽",
        [
            _Cmd("/eat", "從餐點清單隨機推薦一份"),
            _Cmd("/food cat", "列出所有餐點分類"),
            _Cmd("/food show <分類>", "顯示指定分類內的所有餐點"),
        ],
    ),
    _Category(
        "TFT",
        "TFT 戰棋資訊查詢",
        [
            _Cmd("/tft", "查看 TW 伺服器排行榜門檻"),
            _Cmd("/tft <名稱#TAG>", "查詢指定玩家的段位與排名"),
        ],
    ),
    _Category(
        "活動",
        "抽獎與生日相關功能",
        [
            _Cmd("/giveaway", "建立並管理抽獎活動"),
            _Cmd("/bday menu", "生日功能選單（登記 / 訂閱 / 查看）"),
        ],
    ),
]

_MOD_CATEGORY = _Category(
    "管理",
    "需要管理權限的指令",
    [
        _Cmd("/mod clear <數量>", "清除指定數量的訊息（manage_messages）"),
        _Cmd("/mod kick <成員>", "踢出成員（kick_members）"),
        _Cmd("/mod ban <成員>", "封鎖成員（ban_members）"),
        _Cmd("/mod unban <用戶ID>", "解除成員封鎖（ban_members）"),
        _Cmd("/mod mute <成員>", "禁言成員（moderate_members）"),
        _Cmd("/mod unmute <成員>", "解除成員禁言（moderate_members）"),
        _Cmd("/food add <分類> <餐點>", "新增餐點（manage_messages）"),
        _Cmd("/food remove <分類> <餐點>", "移除餐點（manage_messages）"),
    ],
)

_ADMIN_CATEGORY = _Category(
    "管理員",
    "需要伺服器管理員權限的指令",
    [
        _Cmd("/log set <頻道>", "設定日誌記錄頻道"),
        _Cmd("/log unset", "取消日誌記錄頻道設定"),
        _Cmd("/food delete <分類>", "刪除整個餐點分類"),
        _Cmd("/bday init", "初始化伺服器的生日功能"),
    ],
)

_OWNER_CATEGORY = _Category(
    "Bot Owner",
    "Bot Owner 專用指令",
    [
        _Cmd("/cog reload <cog>", "重載指定 Cog"),
        _Cmd("/cog load <cog>", "載入指定 Cog"),
        _Cmd("/cog unload <cog>", "卸載指定 Cog"),
        _Cmd("/cog list", "列出所有已載入的 Cog"),
        _Cmd("/cog sync", "同步指令樹"),
    ],
)


def _build_overview_embed(categories: list[_Category], factory: EmbedFactory) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title=f"{BOT_NAME} 指令列表",
        description="從下方選單選擇分類以查看詳細說明",
        color=discord.Color.blue(),
    )
    for i, cat in enumerate(categories):
        embed.add_field(name=cat.title, value=cat.intro, inline=True)
        # 每兩個 inline field 後插入空白佔位，強制換行，避免三欄過擠
        if i % 2 == 1:
            embed.add_field(name="\u200b", value="\u200b", inline=True)
    return embed


def _build_category_embed(cat: _Category, factory: EmbedFactory) -> discord.Embed:
    embed: discord.Embed = factory.build(
        title=cat.title, description=cat.intro, color=discord.Color.blue()
    )
    value = "\n".join(f"`{cmd.usage}` — {cmd.description}" for cmd in cat.commands)
    embed.add_field(name="指令", value=value, inline=False)
    return embed


_HELP_VIEW_TIMEOUT = 120


class HelpView(UserBoundView):
    def __init__(self, categories: list[_Category], user_id: int, factory: EmbedFactory) -> None:
        super().__init__(user_id, timeout=_HELP_VIEW_TIMEOUT)
        self._embeds = {cat.title: _build_category_embed(cat, factory) for cat in categories}

        options = [
            discord.SelectOption(label=cat.title, description=cat.intro[:100]) for cat in categories
        ]
        self.select: discord.ui.Select = discord.ui.Select(
            placeholder="選擇分類...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self._on_select  # type: ignore[method-assign]
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("這不是你的選單", ephemeral=True)
            return

        await interaction.response.edit_message(
            embed=self._embeds[self.select.values[0]], view=self
        )

    async def on_timeout(self) -> None:
        self.select.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._embed = EmbedFactory.default()

    @app_commands.command(name="ping", description="Bot 延遲")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"延遲: {latency}ms")

    @app_commands.command(name="version", description="Bot 版本資訊")
    async def version(self, interaction: discord.Interaction) -> None:
        python_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

        bot_id = self.bot.user.id if self.bot.user else "Unknown"
        embed = self._embed.build(
            title=f"{BOT_NAME} 版本資訊",
            color=discord.Color.blue(),
            thumbnail=self.bot.user.display_avatar.url if self.bot.user else None,
            footer=f"Bot ID: {bot_id}",
        )
        embed.add_field(name="Bot 版本", value=f"`{BOT_VERSION}`", inline=True)
        embed.add_field(name="Commit", value=f"`{GIT_COMMIT}`", inline=True)
        embed.add_field(name="discord.py", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="Python", value=f"`{python_version}`", inline=True)

        cog_count = len([ext for ext in self.bot.extensions.keys() if "cogs" in ext])
        embed.add_field(
            name="Bot 統計",
            value=(
                f"> 伺服器數: `{len(self.bot.guilds)}`\n"
                f"> 延遲: `{round(self.bot.latency * 1000)}ms`\n"
                f"> 已載入 Cogs: `{cog_count}`"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    info = app_commands.Group(name="info", description="資訊查詢")

    @info.command(name="server", description="伺服器資訊")
    async def info_server(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        embed = self._embed.build(
            title=guild.name,
            description=f"伺服器 ID: {guild.id}",
            color=discord.Color.blue(),
            thumbnail=guild.icon.url if guild.icon else None,
        )
        embed.add_field(
            name="擁有者", value=guild.owner.mention if guild.owner else "未知", inline=True
        )
        embed.add_field(name="成員數", value=str(guild.member_count), inline=True)
        embed.add_field(name="頻道數", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="創建時間", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)

        await interaction.response.send_message(embed=embed)

    @info.command(name="user", description="用戶資訊")
    @app_commands.describe(member="要查詢的用戶（留空為自己）")
    async def info_user(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user

        embed = self._embed.build(
            title=f"{target.display_name} 的資訊",
            color=target.color or discord.Color.default(),
            thumbnail=target.avatar.url if target.avatar else None,
        )
        embed.add_field(name="用戶名", value=str(target), inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)

        if isinstance(target, discord.Member):
            embed.add_field(
                name="加入時間",
                value=target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "未知",
                inline=True,
            )

        embed.add_field(name="帳號創建", value=target.created_at.strftime("%Y-%m-%d"), inline=True)

        if isinstance(target, discord.Member):
            roles = [role.mention for role in target.roles[1:]]
            if roles:
                embed.add_field(name="身分組", value=" ".join(roles[:10]), inline=False)

        await interaction.response.send_message(embed=embed)

    @info.command(name="avatar", description="用戶頭像")
    @app_commands.describe(member="要查詢的用戶（留空為自己）")
    async def info_avatar(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user

        if not target.avatar:
            await interaction.response.send_message("此用戶沒有設定頭像", ephemeral=True)
            return

        embed = self._embed.build(
            title=f"{target.display_name} 的頭像",
            color=target.color or discord.Color.default(),
            image=target.avatar.url,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="顯示所有指令")
    async def help(self, interaction: discord.Interaction) -> None:
        categories: list[_Category] = list(_PUBLIC_CATEGORIES)

        if isinstance(interaction.user, discord.Member):
            perms = interaction.user.guild_permissions
            if any(
                (
                    perms.manage_messages,
                    perms.kick_members,
                    perms.ban_members,
                    perms.moderate_members,
                )
            ):
                categories.append(_MOD_CATEGORY)
            if perms.administrator:
                categories.append(_ADMIN_CATEGORY)

        if interaction.user.id == self.bot.owner_id:
            categories.append(_OWNER_CATEGORY)

        view = HelpView(categories, interaction.user.id, self._embed)
        embed = _build_overview_embed(categories, self._embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityCog(bot))
