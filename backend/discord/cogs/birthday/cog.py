"""Birthday feature cog."""

import asyncio
import calendar
import json
import logging
from datetime import date, datetime, time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import DATA_DIR
from shared.repositories.birthday import BirthdayRepository

from .constants import BIRTHDAY_COLOR, BIRTHDAY_THUMBNAIL, TZ_UTC8
from .views import DashboardView, InitSetupView, UpdateSettingsView

logger = logging.getLogger(__name__)


class BirthdayCog(commands.Cog):
    """生日功能 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.repo: BirthdayRepository
        self._ready = False
        self._embed_config = self._load_embed_config()

    @staticmethod
    def _load_embed_config() -> dict:
        try:
            with open(DATA_DIR / "embed.json", encoding="utf-8") as f:
                return dict(json.load(f))
        except Exception:
            return {}

    def _apply_embed_style(self, embed: discord.Embed) -> discord.Embed:
        """套用 Embed 樣式"""
        if author := self._embed_config.get("author", {}):
            if author.get("name"):
                embed.set_author(
                    name=author["name"],
                    icon_url=author.get("icon_url"),
                    url=author.get("url"),
                )
        embed.set_thumbnail(url=BIRTHDAY_THUMBNAIL)
        return embed

    async def cog_load(self) -> None:
        # 非阻塞載入，讓 Bot 先啟動，後台連接資料庫
        asyncio.create_task(self._connect_db_with_retry())

    async def _connect_db_with_retry(self, max_retries: int = 5, delay: int = 10) -> None:
        """嘗試連接資料庫，失敗時重試"""
        for attempt in range(1, max_retries + 1):
            try:
                pool = self.bot.db_pool  # type: ignore[attr-defined]
                if pool is None:
                    raise RuntimeError("Database pool not initialized on bot")
                self.repo = BirthdayRepository(pool)
                self._ready = True
                self.monthly_birthday_list_task.start()
                self.birthday_notify_task.start()
                self.birthday_role_cleanup_task.start()
                logger.info("Birthday cog loaded")
                return
            except Exception as e:
                logger.warning(
                    f"Birthday DB connection failed ({attempt}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)

        logger.error("Birthday cog failed to connect after all retries")
        self._ready = False

    async def cog_unload(self) -> None:
        self.monthly_birthday_list_task.cancel()
        self.birthday_notify_task.cancel()
        self.birthday_role_cleanup_task.cancel()

    # ==================== Helpers ====================

    async def _fetch_member(self, guild: discord.Guild, user_id: int) -> discord.Member | None:
        """安全取得成員"""
        if member := guild.get_member(user_id):
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    def _get_age(self, birth_year: int) -> int:
        return datetime.now(TZ_UTC8).year - birth_year

    @staticmethod
    def _format_date(month: int, day: int) -> str:
        """格式化日期為 X 月 Y 日"""
        return f"{month} 月 {day} 日"

    def _format_birthday_users(self, members: list[tuple[discord.Member, int | None]]) -> str:
        """格式化壽星列表"""
        parts = []
        for member, age in sorted(members, key=lambda x: x[0].id):
            if age:
                parts.append(f"{member.mention} ({age} 歲)")
            else:
                parts.append(member.mention)
        return "、".join(parts)

    # ==================== Background Tasks ====================

    @tasks.loop(time=time(hour=16, minute=1))  # 00:01 UTC+8
    async def birthday_notify_task(self) -> None:
        if not self._ready:
            return

        now = datetime.now(TZ_UTC8)
        today = now.date()

        # 非閏年 3/1 補發 2/29 生日
        if today.month == 3 and today.day == 1 and not calendar.isleap(today.year):
            await self._send_notifications(today, 2, 29)

        await self._send_notifications(today, today.month, today.day)

    async def _send_notifications(self, today: date, month: int, day: int) -> None:
        try:
            for settings in await self.repo.list_enabled_settings():
                if settings.last_notified_date == today:
                    continue

                guild = self.bot.get_guild(settings.guild_id)
                if not guild:
                    continue

                channel = guild.get_channel(settings.channel_id)
                role = guild.get_role(settings.role_id)

                # 資源失效則停用
                if not channel or not isinstance(channel, discord.TextChannel):
                    await self.repo.update_settings(settings.guild_id, enabled=False)
                    continue
                if not role:
                    await self.repo.update_settings(settings.guild_id, enabled=False)
                    continue

                birthdays = await self.repo.list_todays_birthdays(settings.guild_id, month, day)
                if not birthdays:
                    await self.repo.update_last_notified(settings.guild_id, today)
                    continue

                # 收集壽星並加身分組
                members_with_age: list[tuple[discord.Member, int | None]] = []
                for user_id, birth_year in birthdays:
                    member = await self._fetch_member(guild, user_id)
                    if not member:
                        continue

                    age = self._get_age(birth_year) if birth_year else None
                    members_with_age.append((member, age))

                    try:
                        await member.add_roles(role, reason="Birthday")
                    except discord.Forbidden:
                        logger.warning(f"Cannot add role to {member.id}")

                # 發送通知
                if members_with_age:
                    users_str = self._format_birthday_users(members_with_age)
                    try:
                        await channel.send(settings.message_template.format(users=users_str))
                    except discord.Forbidden:
                        logger.warning(f"Cannot send to channel {channel.id}")

                await self.repo.update_last_notified(settings.guild_id, today)

        except Exception as e:
            logger.error(f"Error in birthday notify: {e}")

    @tasks.loop(time=time(hour=15, minute=59))  # 23:59 UTC+8
    async def birthday_role_cleanup_task(self) -> None:
        if not self._ready:
            return

        try:
            for settings in await self.repo.list_enabled_settings():
                guild = self.bot.get_guild(settings.guild_id)
                if not guild:
                    continue

                role = guild.get_role(settings.role_id)
                if not role or not role.members:
                    continue

                for member in role.members:
                    try:
                        await member.remove_roles(role, reason="Birthday ended")
                        await asyncio.sleep(0.2)  # Rate limit 保護
                    except (discord.Forbidden, discord.HTTPException) as e:
                        logger.warning(f"Cannot remove role: {e}")

        except Exception as e:
            logger.error(f"Error in role cleanup: {e}")

    @tasks.loop(time=time(hour=16, minute=0))  # 00:00 UTC+8
    async def monthly_birthday_list_task(self) -> None:
        """每月 1 日發送當月壽星名單"""
        if not self._ready:
            return

        now = datetime.now(TZ_UTC8)
        if now.day != 1:
            return

        try:
            for settings in await self.repo.list_enabled_settings():
                guild = self.bot.get_guild(settings.guild_id)
                if not guild:
                    continue

                channel = guild.get_channel(settings.channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue

                month_bdays = await self.repo.list_birthdays_in_month(settings.guild_id, now.month)
                if not month_bdays:
                    continue

                # 建立當月壽星 Embed
                lines = []
                for uid, m, d, _ in month_bdays:
                    member = await self._fetch_member(guild, uid)
                    if member:
                        lines.append(f"`{m:>2}/{d:<2}` {member.mention}")

                if not lines:
                    continue

                embed = discord.Embed(
                    title=f"【{now.month} 月壽星名單】",
                    description="\n".join(lines),
                    color=BIRTHDAY_COLOR,
                )
                embed = self._apply_embed_style(embed)

                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    logger.warning(f"Cannot send monthly list to {channel.id}")

        except Exception as e:
            logger.error(f"Error in monthly birthday list: {e}")

    @birthday_notify_task.before_loop
    @birthday_role_cleanup_task.before_loop
    @monthly_birthday_list_task.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    # ==================== Commands ====================

    bday_group = app_commands.Group(name="bday", description="生日相關指令")

    @bday_group.command(name="menu", description="生日功能選單")
    async def bday_menu(self, interaction: discord.Interaction) -> None:
        if not self._ready:
            await interaction.response.send_message("功能尚未就緒", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        if interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True)

        birthday = await self.repo.get_birthday(interaction.user.id)
        is_subscribed = await self.repo.exists_subscription(
            interaction.guild.id, interaction.user.id
        )
        settings = await self.repo.get_settings(interaction.guild.id)

        # 建立 Embed
        embed = discord.Embed(title="【生日功能】", color=BIRTHDAY_COLOR)

        if birthday:
            date_str = self._format_date(birthday.month, birthday.day)
            if birthday.year:
                age = self._get_age(birthday.year)
                bday_val = f"{date_str}\n{age} 歲 ({birthday.year})"
            else:
                bday_val = date_str
        else:
            bday_val = "尚未設定"
        embed.add_field(name="生日", value=bday_val, inline=False)

        if settings:
            embed.add_field(
                name="通知",
                value="已加入" if is_subscribed else "未加入",
                inline=False,
            )
        else:
            embed.add_field(name="通知", value="尚未啟用", inline=False)

        embed = self._apply_embed_style(embed)

        view: DashboardView | None = (
            DashboardView(self, birthday is not None, is_subscribed) if settings else None
        )
        await interaction.followup.send(
            embed=embed,
            view=view,  # type: ignore[arg-type]
        )

    @bday_group.command(name="init", description="初始化伺服器生日功能")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bday_init(self, interaction: discord.Interaction) -> None:
        if not self._ready:
            await interaction.response.send_message("功能尚未就緒", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("此指令只能在伺服器中使用", ephemeral=True)
            return

        if interaction.response.is_done():
            return
        await interaction.response.defer(ephemeral=True)

        settings = await self.repo.get_settings(interaction.guild.id)

        view: discord.ui.View
        if settings:
            # 顯示現有設定
            channel = interaction.guild.get_channel(settings.channel_id)
            role = interaction.guild.get_role(settings.role_id)
            is_healthy = channel and role and settings.enabled

            embed = discord.Embed(
                title="【生日功能設定】",
                description=f"狀態：{'正常' if is_healthy else '**異常**'}",
                color=discord.Color.green() if is_healthy else discord.Color.red(),
            )
            embed.add_field(
                name="通知頻道",
                value=channel.mention if channel else "(已刪除)",
                inline=True,
            )
            embed.add_field(
                name="身分組",
                value=role.mention if role else "(已刪除)",
                inline=True,
            )
            embed.add_field(
                name="通知訊息",
                value=f"`{settings.message_template}`",
                inline=False,
            )
            embed = self._apply_embed_style(embed)

            view = UpdateSettingsView(self, settings)
        else:
            # 新設定
            embed = discord.Embed(
                title="【生日功能設定】",
                description="請選擇設定方式",
                color=BIRTHDAY_COLOR,
            )
            embed = self._apply_embed_style(embed)
            view = InitSetupView(self)

        await interaction.followup.send(embed=embed, view=view)

    # ==================== Public Methods (for Views) ====================

    async def process_birthday_save(
        self,
        interaction: discord.Interaction,
        month: int,
        day: int,
        year: int | None = None,
    ) -> None:
        """處理生日儲存"""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        current_year = datetime.now(TZ_UTC8).year

        # 驗證
        try:
            max_day = calendar.monthrange(current_year, month)[1]
            if not (1 <= month <= 12 and 1 <= day <= max_day):
                await interaction.followup.send(
                    f"日期無效，{month}月最多 {max_day} 天", ephemeral=True
                )
                return
            if year and not (1900 <= year <= current_year):
                await interaction.followup.send(
                    f"年份需在 1900-{current_year} 之間", ephemeral=True
                )
                return
        except Exception:
            await interaction.followup.send("日期驗證失敗", ephemeral=True)
            return

        # 儲存
        is_new = await self.repo.get_birthday(interaction.user.id) is None
        await self.repo.upsert_birthday(interaction.user.id, month, day, year)

        msg = f"生日已設定為 {month:02d}/{day:02d}"
        if year:
            msg += f" ({year}年)"

        # 新用戶自動訂閱
        if is_new and interaction.guild:
            settings = await self.repo.get_settings(interaction.guild.id)
            if settings:
                await self.repo.create_subscription(interaction.guild.id, interaction.user.id)
                msg += f"\n已自動加入 **{interaction.guild.name}** 的生日通知"

        await interaction.followup.send(msg, ephemeral=True)

    async def show_birthday_list(self, interaction: discord.Interaction) -> None:
        """顯示生日列表"""
        if not self._ready or not interaction.guild:
            await interaction.response.send_message("功能尚未就緒", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        settings = await self.repo.get_settings(interaction.guild.id)
        if not settings:
            await interaction.followup.send("此伺服器尚未啟用生日功能")
            return

        now = datetime.now(TZ_UTC8)
        month_bdays = await self.repo.list_birthdays_in_month(interaction.guild.id, now.month)
        upcoming = await self.repo.list_upcoming_birthdays(
            interaction.guild.id, now.month, now.day, limit=3
        )

        embed = discord.Embed(title="【生日列表】", color=BIRTHDAY_COLOR)

        # 本月壽星
        if month_bdays:
            lines = []
            for uid, m, d, _ in month_bdays:
                member = await self._fetch_member(interaction.guild, uid)
                if member:
                    lines.append(f"`{m:>2}/{d:<2}` {member.mention}")
            if lines:
                embed.add_field(name=f"{now.month} 月壽星", value="\n".join(lines), inline=False)

        # 即將到來
        if upcoming:
            lines = []
            for uid, m, d, _ in upcoming:
                member = await self._fetch_member(interaction.guild, uid)
                if member:
                    lines.append(f"`{m:>2}/{d:<2}` {member.mention}")
            if lines:
                embed.add_field(name="即將到來", value="\n".join(lines), inline=False)

        embed = self._apply_embed_style(embed)

        if embed.fields:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("目前沒有生日資料")

    # ==================== Events ====================

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self._ready:
            await self.repo.delete_subscription(member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if self._ready:
            await self.repo.delete_guild_subscriptions(guild.id)
            await self.repo.delete_settings(guild.id)
