"""Birthday feature cog for Discord bot."""

import calendar
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from database import BirthdayRepository, DatabasePool
from discord.ext import commands, tasks

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

# UTC+8 timezone
TZ_UTC8 = timezone(timedelta(hours=8))


class BirthdayModal(discord.ui.Modal, title="設定生日"):
    """Modal for setting birthday."""

    birthday_date = discord.ui.TextInput(
        label="生日日期",
        placeholder="MM/DD (例如: 03/15)",
        required=True,
        min_length=4,
        max_length=5,
    )

    birth_year = discord.ui.TextInput(
        label="出生年份 (選填，填寫即同意顯示年齡)",
        placeholder="YYYY (例如: 1990)",
        required=False,
        min_length=4,
        max_length=4,
    )

    def __init__(self, cog: "BirthdayCog", current_month: Optional[int] = None, current_day: Optional[int] = None, current_year: Optional[int] = None):
        super().__init__()
        self.cog = cog
        # Pre-fill if user has existing data
        if current_month and current_day:
            self.birthday_date.default = f"{current_month:02d}/{current_day:02d}"
        if current_year:
            self.birth_year.default = str(current_year)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Parse date
        date_str = self.birthday_date.value.strip()
        try:
            if "/" in date_str:
                parts = date_str.split("/")
                month = int(parts[0])
                day = int(parts[1])
            else:
                raise ValueError("Invalid format")
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "日期格式錯誤，請使用 MM/DD 格式",
                ephemeral=True,
            )
            return

        # Validate date
        if not (1 <= month <= 12):
            await interaction.response.send_message(
                "月份必須在 1-12 之間",
                ephemeral=True,
            )
            return

        max_day = 31
        if month in [4, 6, 9, 11]:
            max_day = 30
        elif month == 2:
            max_day = 29  # Allow Feb 29

        if not (1 <= day <= max_day):
            await interaction.response.send_message(
                f"{month} 月的日期必須在 1-{max_day} 之間",
                ephemeral=True,
            )
            return

        # Parse year (optional) - empty string means clear the year
        year: Optional[int] = None
        year_str = self.birth_year.value.strip() if self.birth_year.value else ""
        if year_str:
            try:
                year = int(year_str)
                if not (1900 <= year <= 2100):
                    await interaction.response.send_message(
                        "年份必須在 1900-2100 之間",
                        ephemeral=True,
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    "年份格式錯誤，請輸入 4 位數字",
                    ephemeral=True,
                )
                return
        # year is None if field is empty (will clear existing year in DB)

        # Save to database
        await self.cog.repo.set_birthday(interaction.user.id, month, day, year)

        await interaction.response.send_message(
            f"已設定生日為 {month}/{day}" + (f" ({year} 年)" if year else ""),
            ephemeral=True,
        )


class InitSetupView(discord.ui.View):
    """View for init setup flow."""

    def __init__(self, cog: "BirthdayCog"):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id: Optional[int] = None
        self.role_id: Optional[int] = None
        self.create_new = False

    @discord.ui.button(label="使用現有頻道/身分組", style=discord.ButtonStyle.primary)
    async def use_existing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.create_new = False
        # Show channel and role selects
        view = SelectExistingView(self.cog)
        await interaction.response.edit_message(
            content="請選擇要使用的頻道和身分組:",
            view=view,
        )

    @discord.ui.button(label="建立新的", style=discord.ButtonStyle.secondary)
    async def create_new_resources(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild:
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Create channel
            channel = await interaction.guild.create_text_channel(
                name="生日麻吉",
                reason="Birthday feature initialization",
            )

            # Create role with birthday theme color
            role = await interaction.guild.create_role(
                name="今天我生日",
                color=discord.Color.from_str("#FF7F50"),  # 珊瑚橘
                hoist=True,  # 分開顯示
                mentionable=False,
                reason="Birthday feature initialization",
            )

            # Save settings
            await self.cog.repo.create_settings(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
                role_id=role.id,
            )

            await interaction.followup.send(
                f"設定完成\n"
                f"通知頻道: {channel.mention}\n"
                f"生日身分組: {role.mention}",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "Bot 沒有足夠的權限建立頻道或身分組",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Failed to create birthday resources: {e}")
            await interaction.followup.send(
                "建立時發生錯誤，請稍後再試",
                ephemeral=True,
            )


class SelectExistingView(discord.ui.View):
    """View for selecting existing channel and role."""

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
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
        self.channel_id = select.values[0].id
        await interaction.response.defer()
        await self._check_complete(interaction)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="選擇生日身分組",
    )
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect) -> None:
        self.role_id = select.values[0].id
        await interaction.response.defer()
        await self._check_complete(interaction)

    async def _check_complete(self, interaction: discord.Interaction) -> None:
        if self.channel_id and self.role_id and interaction.guild:
            await self.cog.repo.create_settings(
                guild_id=interaction.guild.id,
                channel_id=self.channel_id,
                role_id=self.role_id,
            )

            channel = interaction.guild.get_channel(self.channel_id)
            role = interaction.guild.get_role(self.role_id)

            await interaction.edit_original_response(
                content=f"設定完成\n"
                f"通知頻道: {channel.mention if channel else self.channel_id}\n"
                f"生日身分組: {role.mention if role else self.role_id}",
                view=None,
            )
            self.stop()


class MessageTemplateModal(discord.ui.Modal, title="設定通知訊息"):
    """Modal for setting custom notification message template."""

    template = discord.ui.TextInput(
        label="通知訊息模板 (使用 {users} 代表壽星)",
        placeholder="今天是 {users} 的生日，請各位送上祝福!",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(self, cog: "BirthdayCog", current_template: str, callback):
        super().__init__()
        self.cog = cog
        self.template.default = current_template
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        template = self.template.value.strip()

        # Validate template contains {users}
        if "{users}" not in template:
            await interaction.response.send_message(
                "訊息模板必須包含 {users} 變數",
                ephemeral=True,
            )
            return

        await self.cog.repo.update_settings(
            interaction.guild.id,
            message_template=template,
        )

        await self._callback(interaction, template)


class UpdateSettingsView(discord.ui.View):
    """View for updating existing settings."""

    def __init__(self, cog: "BirthdayCog", settings):
        super().__init__(timeout=300)
        self.cog = cog
        self.settings = settings

    @discord.ui.button(label="修改頻道/身分組", style=discord.ButtonStyle.primary, row=0)
    async def modify_resources(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = SelectExistingView(self.cog)
        # Pre-delete old settings to allow recreation
        if interaction.guild:
            await self.cog.repo.delete_settings(interaction.guild.id)
        await interaction.response.edit_message(
            content="請選擇新的頻道和身分組:",
            view=view,
        )

    @discord.ui.button(label="修改通知訊息", style=discord.ButtonStyle.secondary, row=0)
    async def modify_message(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async def on_template_saved(inter: discord.Interaction, template: str) -> None:
            await inter.response.send_message(
                f"已更新通知訊息:\n`{template}`",
                ephemeral=True,
            )

        modal = MessageTemplateModal(self.cog, self.settings.message_template, on_template_saved)
        await interaction.response.send_modal(modal)


class BirthdayCog(commands.Cog):
    """Birthday feature cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo: BirthdayRepository = None  # type: ignore
        self._ready = False

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        try:
            pool = await DatabasePool.get_pool()
            self.repo = BirthdayRepository(pool)
            self._ready = True
            logger.info("Birthday cog loaded successfully")

            # Start background tasks
            self.birthday_notify_task.start()
            self.birthday_role_cleanup_task.start()

        except Exception as e:
            logger.error(f"Failed to load birthday cog: {e}")
            self._ready = False

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        self.birthday_notify_task.cancel()
        self.birthday_role_cleanup_task.cancel()

    def _is_leap_year(self, year: int) -> bool:
        """Check if a year is a leap year."""
        return calendar.isleap(year)

    def _get_age(self, birth_year: int) -> int:
        """Calculate age from birth year."""
        now = datetime.now(TZ_UTC8)
        return now.year - birth_year

    def _format_birthday_users(self, members: list[tuple[discord.Member, Optional[int]]]) -> str:
        """Format birthday users for notification message."""
        sorted_members = sorted(members, key=lambda x: x[0].id)

        parts = []
        for member, age in sorted_members:
            if age:
                parts.append(f"{member.mention} ({age} 歲)")
            else:
                parts.append(member.mention)

        return "、".join(parts)

    # ==================== Background Tasks ====================

    @tasks.loop(time=time(hour=16, minute=0))  # 00:00 UTC+8 = 16:00 UTC
    async def birthday_notify_task(self) -> None:
        """Send birthday notifications at 00:00 UTC+8."""
        if not self._ready:
            return

        now = datetime.now(TZ_UTC8)
        today = now.date()
        month, day = today.month, today.day

        # Handle Feb 29 in non-leap year
        if month == 3 and day == 1 and not self._is_leap_year(today.year):
            # Also notify Feb 29 birthdays
            await self._send_notifications(today, 2, 29)

        await self._send_notifications(today, month, day)

    async def _send_notifications(self, today: date, month: int, day: int) -> None:
        """Send birthday notifications for a specific date."""
        try:
            all_settings = await self.repo.get_all_enabled_settings()

            for settings in all_settings:
                # Check if already notified today
                if settings.last_notified_date == today:
                    continue

                guild = self.bot.get_guild(settings.guild_id)
                if not guild:
                    continue

                channel = guild.get_channel(settings.channel_id)
                role = guild.get_role(settings.role_id)

                # Validate resources
                if not channel or not isinstance(channel, discord.TextChannel):
                    await self.repo.update_settings(settings.guild_id, enabled=False)
                    continue

                if not role:
                    await self.repo.update_settings(settings.guild_id, enabled=False)
                    continue

                # Get today's birthdays
                birthdays = await self.repo.get_todays_birthdays(
                    settings.guild_id, month, day
                )

                if not birthdays:
                    await self.repo.update_last_notified(settings.guild_id, today)
                    continue

                # Get members and assign roles
                members_with_age: list[tuple[discord.Member, Optional[int]]] = []

                for user_id, birth_year in birthdays:
                    member = guild.get_member(user_id)
                    if not member:
                        continue

                    age = self._get_age(birth_year) if birth_year else None
                    members_with_age.append((member, age))

                    # Assign birthday role
                    try:
                        await member.add_roles(role, reason="Birthday")
                    except discord.Forbidden:
                        logger.warning(f"Cannot add role to {member.id} in {guild.id}")

                if members_with_age:
                    # Format and send message using template
                    users_str = self._format_birthday_users(members_with_age)
                    message = settings.message_template.replace("{users}", users_str)

                    try:
                        await channel.send(message)
                    except discord.Forbidden:
                        logger.warning(f"Cannot send to channel {channel.id}")

                await self.repo.update_last_notified(settings.guild_id, today)

        except Exception as e:
            logger.error(f"Error in birthday notify task: {e}")

    @tasks.loop(time=time(hour=15, minute=59))  # 23:59 UTC+8 = 15:59 UTC
    async def birthday_role_cleanup_task(self) -> None:
        """Remove birthday roles at 23:59 UTC+8."""
        if not self._ready:
            return

        try:
            all_settings = await self.repo.get_all_enabled_settings()

            for settings in all_settings:
                guild = self.bot.get_guild(settings.guild_id)
                if not guild:
                    continue

                role = guild.get_role(settings.role_id)
                if not role:
                    continue

                # Remove role from all members who have it
                for member in role.members:
                    try:
                        await member.remove_roles(role, reason="Birthday ended")
                    except discord.Forbidden:
                        logger.warning(f"Cannot remove role from {member.id}")

        except Exception as e:
            logger.error(f"Error in birthday role cleanup task: {e}")

    @birthday_notify_task.before_loop
    async def before_notify_task(self) -> None:
        """Wait for bot to be ready before starting task."""
        await self.bot.wait_until_ready()

    @birthday_role_cleanup_task.before_loop
    async def before_cleanup_task(self) -> None:
        """Wait for bot to be ready before starting task."""
        await self.bot.wait_until_ready()

    # ==================== Slash Commands ====================

    bday_group = app_commands.Group(name="bday", description="生日相關指令")

    @bday_group.command(name="init", description="初始化伺服器生日功能")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bday_init(self, interaction: discord.Interaction) -> None:
        """Initialize birthday feature for the guild."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        settings = await self.repo.get_settings(interaction.guild.id)

        if settings:
            # Show current settings
            channel = interaction.guild.get_channel(settings.channel_id)
            role = interaction.guild.get_role(settings.role_id)

            channel_status = channel.mention if channel else "(已刪除)"
            role_status = role.mention if role else "(已刪除)"
            status = "正常" if (channel and role and settings.enabled) else "異常"

            view = UpdateSettingsView(self, settings)
            await interaction.response.send_message(
                f"**目前設定**\n"
                f"狀態: {status}\n"
                f"通知頻道: {channel_status}\n"
                f"生日身分組: {role_status}\n"
                f"通知訊息: `{settings.message_template}`",
                view=view,
                ephemeral=True,
            )
        else:
            # New setup
            view = InitSetupView(self)
            await interaction.response.send_message(
                "請選擇設定方式:",
                view=view,
                ephemeral=True,
            )

    @bday_group.command(name="set", description="設定你的生日")
    async def bday_set(self, interaction: discord.Interaction) -> None:
        """Set user's birthday."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        # Get existing data for pre-fill
        existing = await self.repo.get_birthday(interaction.user.id)

        if existing:
            modal = BirthdayModal(
                self,
                current_month=existing.month,
                current_day=existing.day,
                current_year=existing.year,
            )
        else:
            modal = BirthdayModal(self)

        await interaction.response.send_modal(modal)

    @bday_group.command(name="join", description="加入此伺服器的生日通知")
    async def bday_join(self, interaction: discord.Interaction) -> None:
        """Join guild's birthday notifications."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        # Check if guild is initialized
        settings = await self.repo.get_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "此伺服器尚未啟用生日功能",
                ephemeral=True,
            )
            return

        # Check if user has set birthday
        birthday = await self.repo.get_birthday(interaction.user.id)
        if not birthday:
            await interaction.response.send_message(
                "請先使用 /bday set 設定你的生日",
                ephemeral=True,
            )
            return

        # Check if already subscribed
        if await self.repo.is_subscribed(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "你已經加入此伺服器的生日通知",
                ephemeral=True,
            )
            return

        await self.repo.subscribe(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            "已加入此伺服器的生日通知",
            ephemeral=True,
        )

    @bday_group.command(name="leave", description="退出此伺服器的生日通知")
    async def bday_leave(self, interaction: discord.Interaction) -> None:
        """Leave guild's birthday notifications."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        success = await self.repo.unsubscribe(interaction.guild.id, interaction.user.id)

        if success:
            await interaction.response.send_message(
                "已退出此伺服器的生日通知",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "你尚未加入此伺服器的生日通知",
                ephemeral=True,
            )

    @bday_group.command(name="remove", description="刪除你的生日資料")
    async def bday_remove(self, interaction: discord.Interaction) -> None:
        """Remove user's birthday data."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        success = await self.repo.delete_birthday(interaction.user.id)

        if success:
            await interaction.response.send_message(
                "已刪除你的生日資料",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "你尚未設定生日",
                ephemeral=True,
            )

    @bday_group.command(name="test", description="測試生日通知 (管理員)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bday_test(self, interaction: discord.Interaction) -> None:
        """Test birthday notification (admin only)."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        settings = await self.repo.get_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "此伺服器尚未啟用生日功能",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(settings.channel_id)
        role = interaction.guild.get_role(settings.role_id)

        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "通知頻道不存在或無效",
                ephemeral=True,
            )
            return

        if not role:
            await interaction.response.send_message(
                "生日身分組不存在",
                ephemeral=True,
            )
            return

        # Use the command invoker as test subject
        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Get user's actual birthday data for realistic test
        birthday = await self.repo.get_birthday(member.id)
        age: Optional[int] = None
        if birthday and birthday.year:
            age = self._get_age(birthday.year)

        # Format test message
        users_str = self._format_birthday_users([(member, age)])
        message = settings.message_template.replace("{users}", users_str)

        try:
            # Send test notification
            await channel.send(f"[測試] {message}")

            # Temporarily assign role
            await member.add_roles(role, reason="Birthday test")

            await interaction.response.send_message(
                f"已發送測試通知至 {channel.mention}\n"
                f"已暫時給予 {role.mention} 身分組\n"
                f"請使用 /bday test_cleanup 移除測試身分組",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Bot 沒有足夠的權限發送訊息或指派身分組",
                ephemeral=True,
            )

    @bday_group.command(name="test_cleanup", description="移除測試身分組 (管理員)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bday_test_cleanup(self, interaction: discord.Interaction) -> None:
        """Remove test birthday role (admin only)."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        settings = await self.repo.get_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "此伺服器尚未啟用生日功能",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(settings.role_id)
        if not role:
            await interaction.response.send_message(
                "生日身分組不存在",
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        if role not in member.roles:
            await interaction.response.send_message(
                "你目前沒有生日身分組",
                ephemeral=True,
            )
            return

        try:
            await member.remove_roles(role, reason="Birthday test cleanup")
            await interaction.response.send_message(
                "已移除測試身分組",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Bot 沒有足夠的權限移除身分組",
                ephemeral=True,
            )

    @bday_group.command(name="list", description="查看此伺服器的生日列表")
    async def bday_list(self, interaction: discord.Interaction) -> None:
        """List birthdays in the guild."""
        if not self._ready:
            await interaction.response.send_message(
                "功能尚未就緒，請稍後再試",
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "此指令只能在伺服器中使用",
                ephemeral=True,
            )
            return

        settings = await self.repo.get_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "此伺服器尚未啟用生日功能",
                ephemeral=True,
            )
            return

        now = datetime.now(TZ_UTC8)
        current_month = now.month
        current_day = now.day

        # Get this month's birthdays
        month_birthdays = await self.repo.get_birthdays_in_month(
            interaction.guild.id, current_month
        )

        # Get upcoming birthdays
        upcoming = await self.repo.get_upcoming_birthdays(
            interaction.guild.id, current_month, current_day, limit=5
        )

        lines = []

        # This month section
        if month_birthdays:
            lines.append(f"**{current_month} 月壽星**")
            lines.append("─" * 15)
            for user_id, month, day, year in month_birthdays:
                member = interaction.guild.get_member(user_id)
                if member:
                    is_me = " (你)" if user_id == interaction.user.id else ""
                    lines.append(f"{month:02d}/{day:02d}  {member.display_name}{is_me}")
            lines.append("")

        # Upcoming section
        if upcoming:
            lines.append("**即將到來**")
            lines.append("─" * 15)
            for user_id, month, day, year in upcoming:
                member = interaction.guild.get_member(user_id)
                if member:
                    is_me = " (你)" if user_id == interaction.user.id else ""
                    lines.append(f"{month:02d}/{day:02d}  {member.display_name}{is_me}")

        if not lines:
            await interaction.response.send_message(
                "目前沒有生日資料",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
        )

    # ==================== Event Listeners ====================

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Remove subscription when member leaves guild."""
        if not self._ready:
            return

        await self.repo.unsubscribe_user_from_guild(member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Clean up when bot leaves a guild."""
        if not self._ready:
            return

        await self.repo.delete_guild_subscriptions(guild.id)
        await self.repo.delete_settings(guild.id)


async def setup(bot: commands.Bot) -> None:
    """Setup function for the cog."""
    await bot.add_cog(BirthdayCog(bot))
