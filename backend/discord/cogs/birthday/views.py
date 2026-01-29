"""Birthday feature UI components."""

from typing import TYPE_CHECKING, Callable, Optional, Union

import discord

from .constants import BIRTHDAY_COLOR, DEFAULT_MESSAGE_TEMPLATE

if TYPE_CHECKING:
    from .cog import BirthdayCog


def create_setup_complete_embed(
    channel: Optional[Union[discord.abc.GuildChannel, discord.Thread]],
    role: Optional[discord.Role],
) -> discord.Embed:
    """建立設定完成 Embed"""
    embed = discord.Embed(title="【設定完成】", color=discord.Color.green())
    embed.add_field(
        name="通知頻道",
        value=channel.mention if channel else "未知",
        inline=True,
    )
    embed.add_field(
        name="身分組",
        value=role.mention if role else "未知",
        inline=True,
    )
    return embed


class BirthdayModal(discord.ui.Modal, title="設定生日"):
    """生日設定表單"""

    birthday_date: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="生日日期",
        placeholder="MM/DD (例如: 03/15)",
        required=True,
        min_length=4,
        max_length=5,
    )
    birth_year: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="出生年份 (選填，填寫後將顯示年齡)",
        placeholder="YYYY (例如: 2000)",
        required=False,
        min_length=4,
        max_length=4,
    )

    def __init__(self, cog: "BirthdayCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        date_str = self.birthday_date.value.strip()
        try:
            parts = date_str.split("/")
            month, day = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "日期格式錯誤，請使用 MM/DD", ephemeral=True
            )
            return

        year = None
        if self.birth_year.value:
            try:
                year = int(self.birth_year.value.strip())
            except ValueError:
                await interaction.response.send_message(
                    "年份格式錯誤，請輸入 4 位數字", ephemeral=True
                )
                return

        await self.cog.process_birthday_save(interaction, month, day, year)


class MessageTemplateModal(discord.ui.Modal, title="設定通知訊息"):
    """通知訊息模板表單"""

    template: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="通知訊息模板",
        placeholder="使用 {users} 代表壽星",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(
        self,
        cog: "BirthdayCog",
        current_template: str,
        callback: Callable,
    ):
        super().__init__()
        self.cog = cog
        self.template.default = current_template
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        template = self.template.value.strip()
        if "{users}" not in template:
            await interaction.response.send_message(
                "訊息模板必須包含 {users}", ephemeral=True
            )
            return

        await self.cog.repo.update_settings(
            interaction.guild.id, message_template=template
        )
        await self._callback(interaction, template)


class SelectExistingView(discord.ui.View):
    """選擇現有頻道/身分組"""

    def __init__(self, cog: "BirthdayCog"):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id: Optional[int] = None
        self.role_id: Optional[int] = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="選擇通知頻道",
        channel_types=[discord.ChannelType.text],
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        self.channel_id = select.values[0].id
        await interaction.response.defer()
        await self._try_complete(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="選擇身分組")
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        self.role_id = select.values[0].id
        await interaction.response.defer()
        await self._try_complete(interaction)

    async def _try_complete(self, interaction: discord.Interaction) -> None:
        if not (self.channel_id and self.role_id and interaction.guild):
            return

        await self.cog.repo.create_settings(
            guild_id=interaction.guild.id,
            channel_id=self.channel_id,
            role_id=self.role_id,
            message_template=DEFAULT_MESSAGE_TEMPLATE,
        )

        channel = interaction.guild.get_channel(self.channel_id)
        role = interaction.guild.get_role(self.role_id)
        embed = create_setup_complete_embed(channel, role)

        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()


class InitSetupView(discord.ui.View):
    """初始化設定選擇"""

    def __init__(self, cog: "BirthdayCog"):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="使用現有頻道/身分組", style=discord.ButtonStyle.primary)
    async def use_existing(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = discord.Embed(
            title="【生日功能設定】",
            description="請選擇要使用的頻道和身分組",
            color=BIRTHDAY_COLOR,
        )
        await interaction.response.edit_message(
            content=None, embed=embed, view=SelectExistingView(self.cog)
        )

    @discord.ui.button(label="自動建立", style=discord.ButtonStyle.secondary)
    async def create_new(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer(ephemeral=True)

        try:
            from .constants import DEFAULT_CHANNEL_NAME, DEFAULT_ROLE_NAME

            channel = await interaction.guild.create_text_channel(
                name=DEFAULT_CHANNEL_NAME, reason="Birthday feature init"
            )
            role = await interaction.guild.create_role(
                name=DEFAULT_ROLE_NAME,
                color=BIRTHDAY_COLOR,
                hoist=True,
                mentionable=False,
                reason="Birthday feature init",
            )

            await self.cog.repo.create_settings(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
                role_id=role.id,
                message_template=DEFAULT_MESSAGE_TEMPLATE,
            )

            embed = create_setup_complete_embed(channel, role)
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "Bot 權限不足，無法建立頻道或身分組", ephemeral=True
            )
        except Exception:
            await interaction.followup.send("建立時發生錯誤", ephemeral=True)


class UpdateSettingsView(discord.ui.View):
    """更新現有設定"""

    def __init__(self, cog: "BirthdayCog", settings):
        super().__init__(timeout=300)
        self.cog = cog
        self.settings = settings

    @discord.ui.button(label="修改頻道/身分組", style=discord.ButtonStyle.primary)
    async def modify_resources(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = discord.Embed(
            title="【修改設定】",
            description="請選擇新的頻道和身分組",
            color=BIRTHDAY_COLOR,
        )
        await interaction.response.edit_message(
            embed=embed, view=SelectExistingView(self.cog)
        )

    @discord.ui.button(label="修改通知訊息", style=discord.ButtonStyle.secondary)
    async def modify_message(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        async def on_saved(inter: discord.Interaction, template: str) -> None:
            await inter.response.send_message(
                f"已更新通知訊息:\n`{template}`", ephemeral=True
            )

        modal = MessageTemplateModal(
            self.cog, self.settings.message_template, on_saved
        )
        await interaction.response.send_modal(modal)


class DashboardView(discord.ui.View):
    """使用者儀表板"""

    def __init__(self, cog: "BirthdayCog", has_birthday: bool, is_subscribed: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self._is_subscribed = is_subscribed

        # 動態調整按鈕
        self.set_btn.label = "修改生日" if has_birthday else "設定生日"

        if is_subscribed:
            self.toggle_btn.label = "關閉通知"
            self.toggle_btn.style = discord.ButtonStyle.secondary
        else:
            self.toggle_btn.label = "加入通知"
            self.toggle_btn.style = discord.ButtonStyle.success

        if not has_birthday:
            self.remove_item(self.remove_btn)

    @discord.ui.button(label="設定生日", style=discord.ButtonStyle.primary, row=0)
    async def set_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(BirthdayModal(self.cog))

    @discord.ui.button(label="查看列表", style=discord.ButtonStyle.secondary, row=0)
    async def list_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog.show_birthday_list(interaction)

    @discord.ui.button(label="加入通知", style=discord.ButtonStyle.success, row=0)
    async def toggle_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild:
            return

        if self._is_subscribed:
            await self.cog.repo.unsubscribe(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message("已關閉通知", ephemeral=True)
        else:
            birthday = await self.cog.repo.get_birthday(interaction.user.id)
            if not birthday:
                await interaction.response.send_message("請先設定生日", ephemeral=True)
                return
            await self.cog.repo.subscribe(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message("已加入通知", ephemeral=True)

    @discord.ui.button(label="刪除資料", style=discord.ButtonStyle.danger, row=1)
    async def remove_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog.repo.delete_birthday(interaction.user.id)
        await interaction.response.send_message("已刪除生日資料", ephemeral=True)
