import asyncio
import os
from datetime import datetime, timedelta, time
import pytz

import discord
from discord.ext import commands, tasks
from discord import ui

from utils.util import read_json, write_json, now_local, format_datetime, get_data_file_path
from utils.logger import BotLogger

# 常數設定
DEFAULT_WORK_HOURS = 8
DEFAULT_REMINDER_TIME = time(8, 30)  # 08:30 GMT+8
TAIPEI_TZ = pytz.timezone('Asia/Taipei')


class ClockCore:
    """打卡核心邏輯 - 單一職責原則"""
    
    def __init__(self):
        self.active_sessions = {}  # user_id -> session_data
        self.data_file = get_data_file_path("clock_v2.json")
    
    async def initialize(self):
        """初始化數據"""
        try:
            data = await read_json(self.data_file)
            if data:
                # 恢復活躍會話（轉換時間格式）
                for user_id, session in data.get("active_sessions", {}).items():
                    self.active_sessions[int(user_id)] = {
                        "clock_in_time": datetime.fromisoformat(session["clock_in_time"]),
                        "guild_id": session["guild_id"],
                        "channel_id": session["channel_id"]
                    }
            BotLogger.info("ClockCore", f"載入 {len(self.active_sessions)} 個活躍打卡會話")
        except Exception as e:
            BotLogger.error("ClockCore", f"初始化失敗: {e}")
            self.active_sessions = {}
    
    async def save_data(self):
        """保存數據"""
        try:
            data = {
                "active_sessions": {
                    str(user_id): {
                        "clock_in_time": session["clock_in_time"].isoformat(),
                        "guild_id": session["guild_id"],
                        "channel_id": session["channel_id"]
                    }
                    for user_id, session in self.active_sessions.items()
                }
            }
            await write_json(self.data_file, data)
        except Exception as e:
            BotLogger.error("ClockCore", f"保存數據失敗: {e}")
    
    async def smart_clock(self, user_id: int, guild_id: int, channel_id: int, settings: dict) -> dict:
        """
        智能打卡 - 自動判斷上下班
        返回: {"action": "clock_in|clock_out_prompt|status", "data": {...}}
        """
        if user_id not in self.active_sessions:
            # 執行上班打卡
            return await self._clock_in(user_id, guild_id, channel_id, settings)
        else:
            # 已經打卡，計算工作時間並決定動作
            session = self.active_sessions[user_id]
            worked_time = datetime.now() - session["clock_in_time"]
            work_hours = settings.get("work_hours", DEFAULT_WORK_HOURS)
            
            if worked_time.total_seconds() >= work_hours * 3600:
                # 已達到工作時間，提示下班
                return {
                    "action": "clock_out_prompt",
                    "data": {
                        "clock_in_time": session["clock_in_time"],
                        "worked_hours": worked_time.total_seconds() / 3600,
                        "is_overtime": worked_time.total_seconds() > work_hours * 3600
                    }
                }
            else:
                # 顯示當前狀態
                return {
                    "action": "status",
                    "data": {
                        "clock_in_time": session["clock_in_time"],
                        "worked_time": worked_time,
                        "expected_end": session["clock_in_time"] + timedelta(hours=work_hours)
                    }
                }
    
    async def _clock_in(self, user_id: int, guild_id: int, channel_id: int, settings: dict) -> dict:
        """執行上班打卡"""
        clock_time = datetime.now()
        work_hours = settings.get("work_hours", DEFAULT_WORK_HOURS)
        
        self.active_sessions[user_id] = {
            "clock_in_time": clock_time,
            "guild_id": guild_id,
            "channel_id": channel_id
        }
        
        await self.save_data()
        
        return {
            "action": "clock_in",
            "data": {
                "clock_time": clock_time,
                "expected_end": clock_time + timedelta(hours=work_hours),
                "work_hours": work_hours
            }
        }
    
    async def clock_out(self, user_id: int) -> dict:
        """執行下班打卡"""
        if user_id not in self.active_sessions:
            return {"success": False, "error": "尚未打卡"}
        
        session = self.active_sessions.pop(user_id)
        clock_out_time = datetime.now()
        worked_time = clock_out_time - session["clock_in_time"]
        
        await self.save_data()
        
        return {
            "success": True,
            "data": {
                "clock_in_time": session["clock_in_time"],
                "clock_out_time": clock_out_time,
                "worked_time": worked_time,
                "worked_hours": worked_time.total_seconds() / 3600
            }
        }
    
    def get_work_status(self, user_id: int) -> dict:
        """獲取工作狀態"""
        if user_id not in self.active_sessions:
            return {"is_working": False}
        
        session = self.active_sessions[user_id]
        worked_time = datetime.now() - session["clock_in_time"]
        
        return {
            "is_working": True,
            "clock_in_time": session["clock_in_time"],
            "worked_time": worked_time,
            "worked_hours": int(worked_time.total_seconds() // 3600),
            "worked_minutes": int((worked_time.total_seconds() % 3600) // 60)
        }


class ClockSettings:
    """設定管理 - 分層設定系統"""
    
    def __init__(self):
        self.guild_settings = {}
        self.user_settings = {}
        self.settings_file = get_data_file_path("clock_v2_settings.json")
        self.default_settings = {
            "enabled": False,
            "reminder_time": "08:30",
            "reminder_channel": None,
            "work_hours": DEFAULT_WORK_HOURS,
            "timezone": "Asia/Taipei"
        }
    
    async def initialize(self):
        """初始化設定"""
        try:
            data = await read_json(self.settings_file)
            if data:
                # 轉換 guild_id 為整數
                self.guild_settings = {
                    int(guild_id): settings 
                    for guild_id, settings in data.get("guild_settings", {}).items()
                }
                self.user_settings = {
                    int(user_id): settings
                    for user_id, settings in data.get("user_settings", {}).items()
                }
            BotLogger.info("ClockSettings", f"載入 {len(self.guild_settings)} 個伺服器設定")
        except Exception as e:
            BotLogger.error("ClockSettings", f"載入設定失敗: {e}")
    
    async def save_settings(self):
        """保存設定"""
        try:
            data = {
                "guild_settings": {
                    str(guild_id): settings 
                    for guild_id, settings in self.guild_settings.items()
                },
                "user_settings": {
                    str(user_id): settings
                    for user_id, settings in self.user_settings.items()
                }
            }
            await write_json(self.settings_file, data)
        except Exception as e:
            BotLogger.error("ClockSettings", f"保存設定失敗: {e}")
    
    def get_effective_settings(self, user_id: int, guild_id: int) -> dict:
        """獲取生效設定（個人 > 伺服器 > 預設）"""
        settings = self.default_settings.copy()
        
        # 套用伺服器設定
        if guild_id in self.guild_settings:
            settings.update(self.guild_settings[guild_id])
        
        # 套用個人設定（覆蓋伺服器設定）
        if user_id in self.user_settings:
            user_prefs = self.user_settings[user_id]
            for key, value in user_prefs.items():
                if value is not None:  # 只覆蓋有值的設定
                    settings[key] = value
        
        return settings
    
    async def update_guild_settings(self, guild_id: int, **kwargs):
        """更新伺服器設定"""
        if guild_id not in self.guild_settings:
            self.guild_settings[guild_id] = self.default_settings.copy()
        
        self.guild_settings[guild_id].update(kwargs)
        await self.save_settings()
    
    async def update_user_settings(self, user_id: int, **kwargs):
        """更新個人設定"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        
        self.user_settings[user_id].update(kwargs)
        await self.save_settings()
    
    def is_enabled(self, guild_id: int) -> bool:
        """檢查是否啟用"""
        return self.guild_settings.get(guild_id, {}).get("enabled", False)


# ==================== UI 組件 ====================

class SmartClockView(ui.View):
    """智能打卡界面"""
    
    def __init__(self, clock_cog, guild_id: int):
        super().__init__(timeout=3600)  # 1小時超時
        self.clock_cog = clock_cog
        self.guild_id = guild_id
    
    @ui.button(label="🕘 上班打卡", style=discord.ButtonStyle.green)
    async def clock_in_btn(self, interaction: discord.Interaction, button: ui.Button):
        """處理上班打卡"""
        await self.clock_cog.handle_smart_clock_interaction(interaction)
    
    @ui.button(label="⚙️ 個人設定", style=discord.ButtonStyle.grey)
    async def personal_settings_btn(self, interaction: discord.Interaction, button: ui.Button):
        """開啟個人設定"""
        await interaction.response.send_message("🚧 個人設定功能開發中...", ephemeral=True)
    
    async def on_timeout(self):
        """處理超時"""
        for item in self.children:
            item.disabled = True


class ClockOutView(ui.View):
    """下班打卡界面"""
    
    def __init__(self, clock_cog):
        super().__init__(timeout=300)  # 5分鐘超時
        self.clock_cog = clock_cog
    
    @ui.button(label="🕕 下班打卡", style=discord.ButtonStyle.red)
    async def clock_out_btn(self, interaction: discord.Interaction, button: ui.Button):
        """處理下班打卡"""
        await self.clock_cog.handle_clock_out_interaction(interaction)
    
    @ui.button(label="📊 查看工時", style=discord.ButtonStyle.blurple)
    async def view_status_btn(self, interaction: discord.Interaction, button: ui.Button):
        """查看工時狀態"""
        await self.clock_cog.handle_status_interaction(interaction)
    
    @ui.button(label="❌ 取消", style=discord.ButtonStyle.grey)
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button):
        """取消操作"""
        await interaction.response.edit_message(content="操作已取消", embed=None, view=None)


class AdminSetupView(ui.View):
    """管理員設定界面"""
    
    def __init__(self, clock_cog):
        super().__init__(timeout=300)
        self.clock_cog = clock_cog
    
    @ui.select(
        placeholder="選擇要設定的項目...",
        options=[
            discord.SelectOption(label="🔧 啟用/停用系統", value="toggle", emoji="🔧"),
            discord.SelectOption(label="⏰ 設定提醒時間", value="time", emoji="⏰"),
            discord.SelectOption(label="📍 設定提醒頻道", value="channel", emoji="📍"),
            discord.SelectOption(label="⏱️ 設定工作時數", value="hours", emoji="⏱️"),
            discord.SelectOption(label="📊 查看系統狀態", value="status", emoji="📊"),
            discord.SelectOption(label="🧪 測試提醒功能", value="test", emoji="🧪"),
        ]
    )
    async def setup_select(self, interaction: discord.Interaction, select: ui.Select):
        """處理設定選擇"""
        await self.clock_cog.handle_admin_action(interaction, select.values[0])


# ==================== 主要 Cog ====================

class Clock(commands.Cog):
    """Clock V2 - 極簡且強大的打卡系統"""
    
    def __init__(self, bot):
        self.bot = bot
        self.core = ClockCore()
        self.settings = ClockSettings()
        self.reminder_task = None
    
    async def cog_load(self):
        """Cog 載入時初始化"""
        await self.core.initialize()
        await self.settings.initialize()
        
        # 啟動提醒任務
        if not self.reminder_task:
            self.reminder_task = self.daily_reminder.start()
        
        BotLogger.info("Clock", "Clock V2 系統已啟動")
    
    def cog_unload(self):
        """Cog 卸載時清理"""
        if self.reminder_task:
            self.reminder_task.cancel()
    
    # ===== 用戶指令 (極簡化) =====
    
    @commands.hybrid_command(name="clock", aliases=["打卡"])
    async def smart_clock(self, ctx):
        """
        智能打卡 - 自動判斷上下班
        
        • 未打卡時：執行上班打卡
        • 已打卡時：根據工時決定顯示狀態或詢問下班
        """
        if not ctx.guild:
            await ctx.send("❌ 此指令只能在伺服器中使用")
            return
        
        # 檢查是否啟用
        if not self.settings.is_enabled(ctx.guild.id):
            await ctx.send("❌ 此伺服器尚未啟用打卡功能\n請管理員使用 `?clockadmin` 進行設定")
            return
        
        settings = self.settings.get_effective_settings(ctx.author.id, ctx.guild.id)
        result = await self.core.smart_clock(
            ctx.author.id, ctx.guild.id, ctx.channel.id, settings
        )
        
        if result["action"] == "clock_in":
            await self._send_clock_in_success(ctx, result["data"])
        elif result["action"] == "clock_out_prompt":
            await self._send_clock_out_prompt(ctx, result["data"])
        elif result["action"] == "status":
            await self._send_work_status(ctx, result["data"])
    
    @commands.hybrid_command(name="status", aliases=["工時"])
    async def work_status(self, ctx):
        """查看當前工作狀態"""
        status = self.core.get_work_status(ctx.author.id)
        
        if not status["is_working"]:
            await ctx.send("📋 目前沒有打卡記錄")
            return
        
        embed = discord.Embed(
            title="📊 工作狀態",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🕘 打卡時間",
            value=status["clock_in_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="⏱️ 已工作時間",
            value=f"{status['worked_hours']}小時 {status['worked_minutes']}分鐘",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    # ===== 管理員指令 =====
    
    @commands.command(name="clockadmin")
    @commands.has_permissions(manage_guild=True)
    async def admin_panel(self, ctx):
        """打卡系統管理面板"""
        embed = discord.Embed(
            title="⚙️ 打卡系統管理",
            description="選擇要設定的項目",
            color=discord.Color.blue()
        )
        
        # 顯示當前狀態
        is_enabled = self.settings.is_enabled(ctx.guild.id)
        status = "🟢 已啟用" if is_enabled else "🔴 已停用"
        embed.add_field(name="目前狀態", value=status, inline=False)
        
        view = AdminSetupView(self)
        await ctx.send(embed=embed, view=view)
    
    # ===== 內部方法 =====
    
    async def _send_clock_in_success(self, ctx, data):
        """發送上班打卡成功訊息"""
        embed = discord.Embed(
            title="✅ 上班打卡成功",
            color=discord.Color.green(),
            timestamp=data["clock_time"]
        )
        
        embed.add_field(
            name="🕘 打卡時間",
            value=data["clock_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="🏁 預計下班時間",
            value=data["expected_end"].strftime("%H:%M"),
            inline=True
        )
        
        embed.set_footer(text=f"今日工作時間：{data['work_hours']} 小時")
        
        await ctx.send(embed=embed)
        
        BotLogger.command_used(
            "clock_smart", ctx.author.id, ctx.guild.id, "上班打卡成功"
        )
    
    async def _send_clock_out_prompt(self, ctx, data):
        """發送下班打卡詢問"""
        worked_hours = int(data["worked_hours"])
        worked_minutes = int((data["worked_hours"] % 1) * 60)
        
        embed = discord.Embed(
            title="🤔 要下班打卡嗎？",
            description=f"你已經工作了 **{worked_hours}小時 {worked_minutes}分鐘**",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        if data.get("is_overtime"):
            embed.add_field(
                name="⏰ 加班提醒",
                value="已超過標準工時，注意休息！",
                inline=False
            )
        
        view = ClockOutView(self)
        await ctx.send(embed=embed, view=view)
    
    async def _send_work_status(self, ctx, data):
        """發送工作狀態"""
        worked_time = data["worked_time"]
        hours = int(worked_time.total_seconds() // 3600)
        minutes = int((worked_time.total_seconds() % 3600) // 60)
        
        embed = discord.Embed(
            title="📊 目前工作狀態",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🕘 打卡時間",
            value=data["clock_in_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="⏱️ 已工作時間",
            value=f"{hours}小時 {minutes}分鐘",
            inline=True
        )
        
        embed.add_field(
            name="🏁 預計下班時間",
            value=data["expected_end"].strftime("%H:%M"),
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    # ===== 互動處理方法 =====
    
    async def handle_smart_clock_interaction(self, interaction: discord.Interaction):
        """處理智能打卡按鈕互動"""
        settings = self.settings.get_effective_settings(interaction.user.id, interaction.guild.id)
        result = await self.core.smart_clock(
            interaction.user.id, interaction.guild.id, interaction.channel.id, settings
        )
        
        if result["action"] == "clock_in":
            data = result["data"]
            embed = discord.Embed(
                title="✅ 上班打卡成功",
                color=discord.Color.green(),
                timestamp=data["clock_time"]
            )
            embed.add_field(
                name="🕘 打卡時間",
                value=data["clock_time"].strftime("%H:%M"),
                inline=True
            )
            embed.add_field(
                name="🏁 預計下班時間",
                value=data["expected_end"].strftime("%H:%M"),
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("你已經打過卡了！", ephemeral=True)
    
    async def handle_clock_out_interaction(self, interaction: discord.Interaction):
        """處理下班打卡按鈕互動"""
        result = await self.core.clock_out(interaction.user.id)
        
        if result["success"]:
            data = result["data"]
            worked_hours = int(data["worked_hours"])
            worked_minutes = int((data["worked_hours"] % 1) * 60)
            
            embed = discord.Embed(
                title="👋 下班打卡成功",
                color=discord.Color.green(),
                timestamp=data["clock_out_time"]
            )
            embed.add_field(
                name="⏱️ 今日工時",
                value=f"{worked_hours}小時 {worked_minutes}分鐘",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            BotLogger.command_used(
                "clock_out", interaction.user.id, interaction.guild.id, 
                f"下班打卡 - {worked_hours}h{worked_minutes}m"
            )
        else:
            await interaction.response.send_message(
                f"❌ {result['error']}", ephemeral=True
            )
    
    async def handle_status_interaction(self, interaction: discord.Interaction):
        """處理狀態查詢按鈕互動"""
        status = self.core.get_work_status(interaction.user.id)
        
        if status["is_working"]:
            embed = discord.Embed(
                title="📊 工作狀態",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="⏱️ 已工作時間",
                value=f"{status['worked_hours']}小時 {status['worked_minutes']}分鐘",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("目前沒有打卡記錄", ephemeral=True)
    
    async def handle_admin_action(self, interaction: discord.Interaction, action: str):
        """處理管理員操作"""
        guild_id = interaction.guild.id
        
        if action == "toggle":
            # 切換啟用狀態
            current = self.settings.is_enabled(guild_id)
            await self.settings.update_guild_settings(guild_id, enabled=not current)
            
            status = "啟用" if not current else "停用"
            await interaction.response.send_message(f"✅ 打卡系統已{status}", ephemeral=True)
            
        elif action == "status":
            # 顯示狀態
            settings = self.settings.guild_settings.get(guild_id, self.settings.default_settings)
            embed = discord.Embed(title="📊 系統狀態", color=discord.Color.blue())
            
            status = "🟢 已啟用" if settings.get("enabled") else "🔴 已停用"
            embed.add_field(name="狀態", value=status, inline=True)
            embed.add_field(name="提醒時間", value=settings.get("reminder_time", "08:30"), inline=True)
            embed.add_field(name="工作時數", value=f"{settings.get('work_hours', 8)}小時", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        elif action == "test":
            # 測試提醒
            if not self.settings.is_enabled(guild_id):
                await interaction.response.send_message("❌ 請先啟用系統", ephemeral=True)
                return
            
            await self.send_reminder_to_channel(interaction.channel)
            await interaction.response.send_message("✅ 測試提醒已發送", ephemeral=True)
            
        else:
            await interaction.response.send_message("🚧 此功能開發中...", ephemeral=True)
    
    # ===== 定時提醒系統 =====
    
    @tasks.loop(minutes=1)
    async def daily_reminder(self):
        """每日打卡提醒檢查"""
        try:
            now = datetime.now(TAIPEI_TZ)
            current_time = now.time()
            
            for guild in self.bot.guilds:
                if not self.settings.is_enabled(guild.id):
                    continue
                
                settings = self.settings.guild_settings.get(guild.id, {})
                reminder_time_str = settings.get("reminder_time", "08:30")
                
                try:
                    hour, minute = map(int, reminder_time_str.split(":"))
                    reminder_time = time(hour, minute)
                    
                    if (current_time.hour == reminder_time.hour and 
                        current_time.minute == reminder_time.minute):
                        await self.send_daily_reminder(guild, settings)
                        
                except Exception as e:
                    BotLogger.error("Clock", f"處理 {guild.name} 提醒失敗: {e}")
                    
        except Exception as e:
            BotLogger.error("Clock", f"定時提醒錯誤: {e}")
    
    async def send_daily_reminder(self, guild, settings):
        """發送每日打卡提醒"""
        try:
            # 尋找提醒頻道
            channel = None
            if settings.get("reminder_channel"):
                channel = guild.get_channel(settings["reminder_channel"])
            
            if not channel:
                # 自動尋找合適的頻道
                channel = discord.utils.find(
                    lambda c: c.name in ['general', '一般', '打卡', 'clock'] and
                             isinstance(c, discord.TextChannel),
                    guild.channels
                )
            
            if channel:
                await self.send_reminder_to_channel(channel)
                BotLogger.info("Clock", f"發送打卡提醒到 {guild.name}")
                
        except Exception as e:
            BotLogger.error("Clock", f"發送提醒到 {guild.name} 失敗: {e}")
    
    async def send_reminder_to_channel(self, channel):
        """發送提醒到指定頻道"""
        now = datetime.now(TAIPEI_TZ)
        
        embed = discord.Embed(
            title="🕘 上班打卡提醒",
            description=f"早安！現在是 **{now.strftime('%H:%M')}**，該打卡上班囉！",
            color=discord.Color.blue(),
            timestamp=now
        )
        
        embed.add_field(
            name="💡 使用說明",
            value="點擊下方按鈕打卡，或使用 `?clock` 指令",
            inline=False
        )
        
        embed.set_footer(text="⏱️ 此提醒將在 1 小時後失效")
        
        view = SmartClockView(self, channel.guild.id)
        await channel.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Clock(bot))