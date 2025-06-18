import asyncio
import os
from datetime import datetime, timedelta, time
import pytz

import discord
from discord.ext import commands, tasks
from discord.utils import get

from utils.util import read_json, write_json, now_local, format_datetime
from utils.logger import BotLogger

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "clock.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "clock_settings.json")
DEFAULT_WORK_HOURS = 9
DEFAULT_CLOCK_IN_TIME = time(8, 30)  # 08:30 GMT+8
TAIPEI_TZ = pytz.timezone('Asia/Taipei')


def guild_only_check():
    async def predicate(ctx):
        if ctx.guild is None:
            await ctx.send("❌ 此指令只能在伺服器中使用。")
            return False
        return True
    return commands.check(predicate)


class ClockInView(discord.ui.View):
    """打卡互動界面"""
    
    def __init__(self, clock_cog):
        super().__init__(timeout=3600)  # 1小時超時
        self.clock_cog = clock_cog
        self.clocked_users = set()  # 記錄已打卡的用戶
    
    @discord.ui.button(label="上班打卡", style=discord.ButtonStyle.green, emoji="🕘")
    async def clock_in_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """處理打卡按鈕點擊"""
        await self.clock_cog.handle_clock_in_interaction(interaction, self)
    
    async def on_timeout(self):
        """處理超時"""
        # 禁用所有按鈕
        for item in self.children:
            item.disabled = True
        
        # 更新 embed 顯示超時
        embed = discord.Embed(
            title="⏰ 打卡時間已結束",
            description="打卡提醒已超時，請使用 `?cin` 手動打卡",
            color=discord.Color.orange()
        )
        
        # 嘗試編輯原始訊息
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(embed=embed, view=self)
        except:
            pass


class Clock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.clocked_in = {}  # user_id -> {"time": datetime, "channel_id": int}
        self.reminded_10min = set()
        self.loop_task = None
        self.guild_settings = {}  # guild_id -> settings dict
        self.daily_reminder_sent = {}  # guild_id -> bool 防止重複發送提醒

    async def initialize(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # 載入打卡資料
        if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
            await write_json(DATA_FILE, {})
            self.clocked_in = {}
        else:
            raw_data = await read_json(DATA_FILE) or {}
            self.clocked_in = {
                int(uid): {
                    "time": datetime.fromisoformat(info["time"]),
                    "channel_id": info["channel_id"]
                }
                for uid, info in raw_data.items()
            }
        
        # 載入設定資料
        await self.load_guild_settings()

    async def save_clock_data(self):
        to_save = {
            str(uid): {
                "time": info["time"].isoformat(),
                "channel_id": info["channel_id"]
            }
            for uid, info in self.clocked_in.items()
        }
        await write_json(DATA_FILE, to_save)
    
    async def load_guild_settings(self):
        """載入公會設定"""
        try:
            if not os.path.exists(SETTINGS_FILE):
                # 創建預設設定檔
                default_data = {
                    "guild_settings": {},
                    "default_settings": {
                        "enabled": False,
                        "reminder_time": "08:30",
                        "reminder_channel": None,
                        "work_hours": DEFAULT_WORK_HOURS,
                        "timezone": "Asia/Taipei"
                    }
                }
                await write_json(SETTINGS_FILE, default_data)
                self.guild_settings = {}
                return
            
            settings_data = await read_json(SETTINGS_FILE) or {}
            guild_settings = settings_data.get("guild_settings", {})
            
            # 轉換 guild_id 為整數
            self.guild_settings = {
                int(guild_id): settings 
                for guild_id, settings in guild_settings.items()
            }
            
            BotLogger.info("Clock", f"載入 {len(self.guild_settings)} 個公會的打卡設定")
            
        except Exception as e:
            BotLogger.error("Clock", f"載入公會設定失敗: {e}")
            self.guild_settings = {}
    
    async def save_guild_settings(self):
        """儲存公會設定"""
        try:
            # 讀取現有資料
            if os.path.exists(SETTINGS_FILE):
                settings_data = await read_json(SETTINGS_FILE) or {}
            else:
                settings_data = {"default_settings": {}}
            
            # 更新公會設定（轉換 guild_id 為字串）
            settings_data["guild_settings"] = {
                str(guild_id): settings 
                for guild_id, settings in self.guild_settings.items()
            }
            
            await write_json(SETTINGS_FILE, settings_data)
            BotLogger.info("Clock", "公會設定已儲存")
            
        except Exception as e:
            BotLogger.error("Clock", f"儲存公會設定失敗: {e}")
            raise
    
    def get_guild_settings(self, guild_id: int) -> dict:
        """獲取公會設定，如果不存在則返回預設值"""
        return self.guild_settings.get(guild_id, {
            "enabled": False,
            "reminder_time": "08:30",
            "reminder_channel": None,
            "work_hours": DEFAULT_WORK_HOURS,
            "timezone": "Asia/Taipei"
        })
    
    def is_clock_enabled(self, guild_id: int) -> bool:
        """檢查公會是否啟用打卡功能"""
        settings = self.get_guild_settings(guild_id)
        return settings.get("enabled", False)

    @commands.Cog.listener()
    async def on_ready(self):
        if self.loop_task is None:
            await self.initialize()
            BotLogger.info("Clock", "打卡資料載入完成")
            self.loop_task = self.bot.loop.create_task(self.check_clock_loop())
            # 啟動定時打卡提醒
            self.daily_clock_reminder.start()
    
    @tasks.loop(minutes=1)
    async def daily_clock_reminder(self):
        """每分鐘檢查是否需要發送打卡提醒"""
        try:
            now_taipei = datetime.now(TAIPEI_TZ)
            current_time = now_taipei.time()
            
            # 檢查是否為打卡時間並發送提醒
            for guild in self.bot.guilds:
                guild_id = guild.id
                settings = self.get_guild_settings(guild_id)
                
                # 檢查公會是否啟用打卡功能
                if not settings.get("enabled", False):
                    continue
                
                # 解析提醒時間
                reminder_time_str = settings.get("reminder_time", "08:30")
                try:
                    reminder_hour, reminder_minute = map(int, reminder_time_str.split(":"))
                    reminder_time = time(reminder_hour, reminder_minute)
                except:
                    reminder_time = DEFAULT_CLOCK_IN_TIME
                
                # 檢查是否為該公會的打卡時間
                if (current_time.hour == reminder_time.hour and 
                    current_time.minute == reminder_time.minute and
                    not self.daily_reminder_sent.get(guild_id, False)):
                    
                    await self.send_guild_clock_in_reminder(guild)
                    self.daily_reminder_sent[guild_id] = True
                    BotLogger.info("Clock", f"發送 {guild.name} 的每日打卡提醒")
            
            # 重置每日提醒標記 (在00:00時)
            if current_time.hour == 0 and current_time.minute == 0:
                self.daily_reminder_sent = {}
                
        except Exception as e:
            BotLogger.error("Clock", f"定時打卡提醒錯誤: {e}")
    
    async def send_guild_clock_in_reminder(self, guild):
        """發送打卡提醒到指定公會"""
        try:
            settings = self.get_guild_settings(guild.id)
            
            # 獲取指定頻道或尋找適合的頻道
            channel = None
            if settings.get("reminder_channel"):
                channel = guild.get_channel(settings["reminder_channel"])
            
            if not channel:
                # 嘗試在一般頻道發送
                channel = discord.utils.find(
                    lambda c: c.name in ['general', '一般', '打卡', 'clock'] and 
                             isinstance(c, discord.TextChannel), 
                    guild.channels
                )
                
            if not channel:
                # 如果找不到特定頻道，使用第一個文字頻道
                channel = next((c for c in guild.channels if isinstance(c, discord.TextChannel)), None)
            
            if channel:
                await self.send_clock_in_embed(channel, settings)
                
        except Exception as e:
            BotLogger.error("Clock", f"發送打卡提醒到 {guild.name} 失敗: {e}")
    
    async def send_clock_in_embed(self, channel, settings=None):
        """發送互動式打卡 embed"""
        now_taipei = datetime.now(TAIPEI_TZ)
        
        if settings is None:
            settings = self.get_guild_settings(channel.guild.id)
        
        work_hours = settings.get("work_hours", DEFAULT_WORK_HOURS)
        
        embed = discord.Embed(
            title="🕘 上班打卡提醒",
            description=f"早安！現在是 **{now_taipei.strftime('%H:%M')}**，該打卡上班囉！",
            color=discord.Color.blue(),
            timestamp=now_taipei
        )
        
        embed.add_field(
            name="⏰ 工作時間",
            value=f"{work_hours} 小時",
            inline=True
        )
        
        embed.add_field(
            name="🏁 預計下班時間",
            value=f"{(now_taipei + timedelta(hours=work_hours)).strftime('%H:%M')}",
            inline=True
        )
        
        embed.add_field(
            name="📋 使用說明",
            value="點擊下方按鈕進行打卡\n打卡後會自動開始工時計算",
            inline=False
        )
        
        embed.set_footer(text="⏱️ 此提醒將在 1 小時後自動失效")
        
        view = ClockInView(self)
        message = await channel.send(embed=embed, view=view)
        view.message = message  # 儲存訊息參考以便超時時編輯

    async def check_clock_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = now_local()
                to_remove = []

                for uid, info in list(self.clocked_in.items()):
                    start_time = info["time"]
                    end_time = start_time + timedelta(hours=WORK_HOURS)
                    channel = self.bot.get_channel(info["channel_id"])
                    if channel is None:
                        continue
                    member = get(channel.guild.members, id=uid)
                    if member is None:
                        continue

                    time_left = (end_time - now).total_seconds()

                    if 0 < time_left <= 600 and uid not in self.reminded_10min:
                        await channel.send(f"⌛ {member.mention} 還有 10 分鐘就下班囉！")
                        self.reminded_10min.add(uid)

                    elif time_left <= 0:
                        await channel.send(
                            f"🔔 {member.mention} 該下班囉！\n已經是 **{format_datetime(now)}** 啦！"
                        )
                        to_remove.append(uid)

                for uid in to_remove:
                    self.clocked_in.pop(uid, None)
                    self.reminded_10min.discard(uid)

                if to_remove:
                    await self.save_clock_data()

                await asyncio.sleep(60)
            except Exception as e:
                BotLogger.error("Clock", f"check_clock_loop 錯誤: {e}")
                await asyncio.sleep(60)
    
    async def handle_clock_in_interaction(self, interaction: discord.Interaction, view: ClockInView):
        """處理打卡按鈕互動"""
        uid = interaction.user.id
        now = now_local()
        
        # 檢查打卡功能是否啟用
        if not self.is_clock_enabled(interaction.guild.id):
            await interaction.response.send_message(
                "❌ 此伺服器尚未啟用打卡功能。請聯絡管理員使用 `?clock_setup` 進行設定。",
                ephemeral=True
            )
            return
        
        # 檢查是否已經打卡
        if uid in self.clocked_in:
            old_time = self.clocked_in[uid]["time"]
            await interaction.response.send_message(
                f"🕒 {interaction.user.mention} 你已經打過卡了（{format_datetime(old_time)}）",
                ephemeral=True
            )
            return
        
        # 執行打卡
        self.clocked_in[uid] = {"time": now, "channel_id": interaction.channel.id}
        await self.save_clock_data()
        view.clocked_users.add(uid)
        
        settings = self.get_guild_settings(interaction.guild.id)
        work_hours = settings.get("work_hours", DEFAULT_WORK_HOURS)
        end_time = now + timedelta(hours=work_hours)
        
        # 創建打卡成功 embed
        embed = discord.Embed(
            title="✅ 打卡成功！",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        embed.add_field(
            name="🕑 打卡時間", 
            value=format_datetime(now), 
            inline=False
        )
        embed.add_field(
            name="⏰ 預計下班時間", 
            value=format_datetime(end_time), 
            inline=False
        )
        embed.set_footer(text=f"工作時間為 {work_hours} 小時")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        BotLogger.command_used(
            "clock_in_button", 
            uid, 
            interaction.guild.id if interaction.guild else 0, 
            f"按鈕打卡成功"
        )

    @commands.command(name="cin", help="上班打卡")
    @guild_only_check()
    async def clock_in(self, ctx: commands.Context):
        # 檢查打卡功能是否啟用
        if not self.is_clock_enabled(ctx.guild.id):
            await ctx.send("❌ 此伺服器尚未啟用打卡功能。請聯絡管理員使用 `?clock_setup` 進行設定。")
            return
        
        uid = ctx.author.id
        now = now_local()

        if uid in self.clocked_in:
            old_time = self.clocked_in[uid]["time"]
            await ctx.send(
                f"🕒 {ctx.author.mention} 你已經打過卡了（{format_datetime(old_time)}）"
            )
            return

        self.clocked_in[uid] = {"time": now, "channel_id": ctx.channel.id}
        await self.save_clock_data()
        
        settings = self.get_guild_settings(ctx.guild.id)
        work_hours = settings.get("work_hours", DEFAULT_WORK_HOURS)
        end_time = now + timedelta(hours=work_hours)

        embed = discord.Embed(
            title="✅ 打卡成功！",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_author(name=ctx.author.display_name,
                         icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.add_field(
            name="🕑 打卡時間", value=format_datetime(now), inline=False)
        embed.add_field(name="⏰ 預計下班時間", value=format_datetime(
            end_time), inline=False)
        embed.set_footer(text=f"工作時間為 {work_hours} 小時")

        await ctx.send(embed=embed)
        
        BotLogger.command_used(
            "cin", 
            ctx.author.id, 
            ctx.guild.id if ctx.guild else 0, 
            "手動打卡成功"
        )

    @commands.command(name="cout", help="下班打卡")
    @guild_only_check()
    async def clock_out(self, ctx: commands.Context):
        uid = ctx.author.id
        now = now_local()

        if uid not in self.clocked_in:
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有打卡，無法下班。")
            return

        start_time = self.clocked_in.pop(uid)["time"]
        self.reminded_10min.discard(uid)
        await self.save_clock_data()

        worked_time = now - start_time
        hours, remainder = divmod(worked_time.total_seconds(), 3600)
        minutes, _ = divmod(remainder, 60)

        await ctx.send(
            f"👋 {ctx.author.mention} 下班成功！\n"
            f"🕒 工作時長：**{int(hours)} 小時 {int(minutes)} 分鐘**"
        )
        
        BotLogger.command_used(
            "cout", 
            ctx.author.id, 
            ctx.guild.id if ctx.guild else 0, 
            f"下班 - 工時: {int(hours)}h{int(minutes)}m"
        )

    @commands.command(name="wS", help="查詢目前上班狀態")
    @guild_only_check()
    async def check_status(self, ctx: commands.Context):
        uid = ctx.author.id
        if uid not in self.clocked_in:
            await ctx.send(f"📋 {ctx.author.mention} 你目前沒有打卡。")
        else:
            start_time = self.clocked_in[uid]["time"]
            now = now_local()
            elapsed = now - start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(
                f"🕒 {ctx.author.mention} \n你於 **{format_datetime(start_time)}** 打卡，\n"
                f"目前已工作 **{int(hours)} 小時 {int(minutes)} 分鐘**。"
            )
    
    @commands.command(name="clock_setup", help="設定打卡系統 (管理員專用)")
    @guild_only_check()
    @commands.has_permissions(manage_guild=True)
    async def clock_setup(self, ctx: commands.Context, action: str = None, *, value: str = None):
        """
        打卡系統設定指令
        
        使用方式:
        ?clock_setup enable - 啟用打卡功能
        ?clock_setup disable - 停用打卡功能
        ?clock_setup time HH:MM - 設定提醒時間 (如: 08:30)
        ?clock_setup hours N - 設定工作時數 (如: 9)
        ?clock_setup channel #頻道 - 設定提醒頻道
        ?clock_setup status - 查看目前設定
        """
        guild_id = ctx.guild.id
        
        if action is None:
            await self.show_clock_setup_help(ctx)
            return
        
        try:
            settings = self.get_guild_settings(guild_id).copy()
            
            if action == "enable":
                settings["enabled"] = True
                settings["enabled_by"] = ctx.author.id
                settings["enabled_at"] = datetime.now().isoformat()
                self.guild_settings[guild_id] = settings
                await self.save_guild_settings()
                
                await ctx.send("✅ 打卡功能已啟用！\n💡 使用 `?clock_setup status` 查看完整設定")
                
            elif action == "disable":
                settings["enabled"] = False
                self.guild_settings[guild_id] = settings
                await self.save_guild_settings()
                
                await ctx.send("⏹️ 打卡功能已停用")
                
            elif action == "time":
                if not value:
                    await ctx.send("❌ 請提供時間格式，例如：`?clock_setup time 08:30`")
                    return
                
                try:
                    hour, minute = map(int, value.split(":"))
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError("時間範圍錯誤")
                    
                    settings["reminder_time"] = f"{hour:02d}:{minute:02d}"
                    self.guild_settings[guild_id] = settings
                    await self.save_guild_settings()
                    
                    await ctx.send(f"⏰ 提醒時間已設定為 {settings['reminder_time']}")
                    
                except ValueError:
                    await ctx.send("❌ 時間格式錯誤，請使用 HH:MM 格式 (如: 08:30)")
                    
            elif action == "hours":
                if not value:
                    await ctx.send("❌ 請提供工作時數，例如：`?clock_setup hours 9`")
                    return
                
                try:
                    work_hours = int(value)
                    if not (1 <= work_hours <= 24):
                        raise ValueError("工作時數必須在1-24小時之間")
                    
                    settings["work_hours"] = work_hours
                    self.guild_settings[guild_id] = settings
                    await self.save_guild_settings()
                    
                    await ctx.send(f"⏱️ 工作時數已設定為 {work_hours} 小時")
                    
                except ValueError as e:
                    await ctx.send(f"❌ {e}")
                    
            elif action == "channel":
                if not value:
                    settings["reminder_channel"] = None
                    message = "📍 提醒頻道已重置，將自動選擇適合的頻道"
                else:
                    # 解析頻道
                    channel = None
                    if value.startswith("<#") and value.endswith(">"):
                        try:
                            channel_id = int(value[2:-1])
                            channel = ctx.guild.get_channel(channel_id)
                        except:
                            pass
                    
                    if not channel:
                        await ctx.send("❌ 找不到指定的頻道，請使用 #頻道名稱 格式")
                        return
                    
                    settings["reminder_channel"] = channel.id
                    message = f"📍 提醒頻道已設定為 {channel.mention}"
                
                self.guild_settings[guild_id] = settings
                await self.save_guild_settings()
                await ctx.send(message)
                
            elif action == "status":
                await self.show_clock_status(ctx, settings)
                
            else:
                await ctx.send("❌ 未知的設定選項，使用 `?clock_setup` 查看幫助")
                
        except Exception as e:
            await ctx.send(f"❌ 設定時發生錯誤: {e}")
            BotLogger.error("Clock", f"clock_setup 錯誤: {e}")
    
    async def show_clock_setup_help(self, ctx):
        """顯示設定幫助"""
        embed = discord.Embed(
            title="⚙️ 打卡系統設定",
            description="管理員可以使用以下指令設定打卡系統",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔧 基本設定",
            value="`?clock_setup enable` - 啟用打卡功能\n"
                  "`?clock_setup disable` - 停用打卡功能\n"
                  "`?clock_setup status` - 查看目前設定",
            inline=False
        )
        
        embed.add_field(
            name="⏰ 進階設定",
            value="`?clock_setup time 08:30` - 設定提醒時間\n"
                  "`?clock_setup hours 9` - 設定工作時數\n"
                  "`?clock_setup channel #頻道` - 設定提醒頻道",
            inline=False
        )
        
        embed.add_field(
            name="💡 注意事項",
            value="• 預設為停用狀態，需手動啟用\n"
                  "• 提醒時間使用 GMT+8 時區\n"
                  "• 需要「管理伺服器」權限",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    async def show_clock_status(self, ctx, settings):
        """顯示目前設定狀態"""
        embed = discord.Embed(
            title="📊 打卡系統狀態",
            color=discord.Color.green() if settings["enabled"] else discord.Color.red()
        )
        
        status = "🟢 已啟用" if settings["enabled"] else "🔴 已停用"
        embed.add_field(name="狀態", value=status, inline=True)
        
        embed.add_field(
            name="提醒時間", 
            value=f"⏰ {settings.get('reminder_time', '08:30')}", 
            inline=True
        )
        
        embed.add_field(
            name="工作時數", 
            value=f"⏱️ {settings.get('work_hours', DEFAULT_WORK_HOURS)} 小時", 
            inline=True
        )
        
        # 提醒頻道
        channel_id = settings.get("reminder_channel")
        if channel_id:
            channel = ctx.guild.get_channel(channel_id)
            channel_text = channel.mention if channel else "❌ 頻道不存在"
        else:
            channel_text = "🤖 自動選擇"
        
        embed.add_field(name="提醒頻道", value=channel_text, inline=True)
        
        # 啟用資訊
        if settings["enabled"]:
            enabled_at = settings.get("enabled_at")
            if enabled_at:
                try:
                    enabled_time = datetime.fromisoformat(enabled_at)
                    embed.set_footer(text=f"啟用時間: {enabled_time.strftime('%Y-%m-%d %H:%M')}")
                except:
                    pass
        
        await ctx.send(embed=embed)
    
    @clock_setup.error
    async def clock_setup_error(self, ctx, error):
        """處理設定指令錯誤"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 您需要「管理伺服器」權限才能使用此指令")
        else:
            await ctx.send("❌ 指令執行時發生錯誤")
            BotLogger.error("Clock", f"clock_setup 錯誤: {error}")
    
    @commands.command(name="clock_test", help="測試打卡提醒 (管理員專用)")
    @guild_only_check()
    @commands.has_permissions(manage_guild=True)
    async def test_clock_reminder(self, ctx: commands.Context):
        """測試用指令：立即發送打卡提醒"""
        if not self.is_clock_enabled(ctx.guild.id):
            await ctx.send("❌ 打卡功能尚未啟用，請先使用 `?clock_setup enable`")
            return
            
        try:
            await self.send_clock_in_embed(ctx.channel)
            await ctx.send("✅ 測試打卡提醒已發送")
            
            BotLogger.command_used(
                "clock_test", 
                ctx.author.id, 
                ctx.guild.id if ctx.guild else 0, 
                "測試打卡提醒"
            )
        except Exception as e:
            await ctx.send(f"❌ 發送測試提醒失敗: {e}")
            BotLogger.error("Clock", f"測試打卡提醒失敗: {e}")
    
    def cog_unload(self):
        """卸載時停止定時任務"""
        if hasattr(self, 'daily_clock_reminder'):
            self.daily_clock_reminder.cancel()
        if self.loop_task:
            self.loop_task.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Clock(bot))
