import os
from datetime import datetime, timedelta, time
import pytz
import re

import discord
from discord.ext import commands, tasks
from discord import ui

from utils.util import read_json, write_json, now_local, format_datetime, get_data_file_path
from utils.logger import BotLogger

# 常數設定
DEFAULT_WORK_HOURS = 8
DEFAULT_REMINDER_TIME = time(8, 30)  # 08:30 GMT+8
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# 個人化打卡系統常數
PERSONAL_CLOCK_COLORS = {
    "success": discord.Color.green(),
    "warning": discord.Color.orange(), 
    "info": discord.Color.blue(),
    "reminder": discord.Color.purple(),
    "error": discord.Color.red(),
    "neutral": discord.Color.light_grey()
}


# ==================== 工具函數 ====================

def create_work_details_embed(status: dict) -> discord.Embed:
    """建立工作詳情Embed - 獨立工具函數"""
    embed = discord.Embed(
        title="📊 工作狀態詳情",
        color=PERSONAL_CLOCK_COLORS["info"]
    )
    
    embed.add_field(
        name="🕘 上班時間",
        value=status["clock_in_time"].strftime("%H:%M"),
        inline=True
    )
    
    embed.add_field(
        name="📊 打卡狀態",
        value=f"{'✅ 正常' if status['clock_in_status'] == '正常' else '⚠️ ' + status['clock_in_status']}",
        inline=True
    )
    
    embed.add_field(
        name="⏱️ 已工作時間",
        value=f"{status['worked_hours']}小時 {status['worked_minutes']}分鐘",
        inline=True
    )
    
    embed.add_field(
        name="🏁 預計下班時間",
        value=status["expected_end"].strftime("%H:%M"),
        inline=True
    )
    
    embed.add_field(
        name="📈 設定工時",
        value=f"{status['settings']['work_hours']} 小時",
        inline=True
    )
    
    # 計算進度百分比
    target_seconds = status['settings']['work_hours'] * 3600
    current_seconds = status['worked_time'].total_seconds()
    progress = min(100, (current_seconds / target_seconds) * 100)
    
    embed.add_field(
        name="📈 工時進度",
        value=f"{progress:.1f}%",
        inline=True
    )
    
    return embed


# 舊系統 ClockCore 已移除 - 使用 PersonalClockCore 替代


class PersonalClockCore:
    """個人化打卡核心邏輯"""
    
    def __init__(self):
        self.users_dir = get_data_file_path("clock_users")
        self.ensure_users_directory()
    
    def ensure_users_directory(self):
        """確保用戶目錄存在"""
        try:
            if not os.path.exists(self.users_dir):
                os.makedirs(self.users_dir)
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"建立用戶目錄失敗: {e}")
    
    def get_user_file_path(self, user_id: int) -> str:
        """獲取用戶數據檔案路徑"""
        return os.path.join(self.users_dir, f"clock_user_{user_id}.json")
    
    async def load_user_data(self, user_id: int) -> dict:
        """載入用戶數據"""
        try:
            file_path = self.get_user_file_path(user_id)
            data = await read_json(file_path)
            return data if data else self.get_default_user_data(user_id)
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"載入用戶 {user_id} 數據失敗: {e}")
            return self.get_default_user_data(user_id)
    
    def get_default_user_data(self, user_id: int) -> dict:
        """獲取預設用戶數據結構"""
        return {
            "user_info": {
                "user_id": user_id,
                "setup_completed": False,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "settings": {
                "work_start_time": "08:30",
                "work_hours": 8.0,
                "flexible_clock_in": False,
                "flex_window_minutes": 30,
                "clock_out_window": 15,
                "timezone": "Asia/Taipei",
                "enabled": False
            },
            "active_session": {
                "is_working": False,
                "clock_in_time": None,
                "clock_in_status": None,
                "expected_clock_out": None,
                "guild_id": None,
                "channel_id": None
            },
            "records": {
                "daily": {}
            }
        }
    
    async def save_user_data(self, user_id: int, data: dict):
        """保存用戶數據"""
        try:
            data["user_info"]["last_updated"] = datetime.now().isoformat()
            file_path = self.get_user_file_path(user_id)
            await write_json(file_path, data)
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"保存用戶 {user_id} 數據失敗: {e}")
    
    def get_clock_timing(self, settings: dict) -> dict:
        """計算打卡相關時間點"""
        try:
            start_time_str = settings.get("work_start_time", "08:30")
            hour, minute = map(int, start_time_str.split(":"))
            base_time = time(hour, minute)
            
            flex_enabled = settings.get("flexible_clock_in", False)
            flex_window = settings.get("flex_window_minutes", 30)
            
            if flex_enabled:
                # 彈性模式 - 使用datetime計算避免跨日問題
                reminder_time = base_time
                base_datetime = datetime.combine(datetime.now().date(), base_time)
                late_threshold_datetime = base_datetime + timedelta(minutes=flex_window)
                late_threshold_time = late_threshold_datetime.time()
                view_timeout = flex_window * 60
            else:
                # 定點模式 - 使用datetime計算避免跨日問題
                reminder_time = base_time
                base_datetime = datetime.combine(datetime.now().date(), base_time)
                late_threshold_datetime = base_datetime + timedelta(minutes=1)
                late_threshold_time = late_threshold_datetime.time()
                view_timeout = 30 * 60
            
            return {
                "reminder_time": reminder_time,
                "late_threshold_time": late_threshold_time,
                "view_timeout": view_timeout,
                "flex_enabled": flex_enabled,
                "flex_window": flex_window
            }
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"計算時間點失敗: {e}")
            return {
                "reminder_time": time(8, 30),
                "late_threshold_time": time(8, 31),
                "view_timeout": 1800,
                "flex_enabled": False,
                "flex_window": 30
            }
    
    def calculate_clock_in_status(self, clock_in_time: datetime, settings: dict) -> dict:
        """計算打卡狀態"""
        timing = self.get_clock_timing(settings)
        
        # 獲取今天的遲到判定時間
        today = clock_in_time.date()
        late_threshold_datetime = datetime.combine(today, timing["late_threshold_time"])
        
        if clock_in_time < late_threshold_datetime:
            return {
                "status": "正常",
                "status_color": "success",
                "late_minutes": 0
            }
        else:
            late_minutes = (clock_in_time - late_threshold_datetime).total_seconds() / 60
            return {
                "status": "遲到",
                "status_color": "warning",
                "late_minutes": int(late_minutes)
            }
    
    async def clock_in(self, user_id: int, guild_id: int, channel_id: int) -> dict:
        """執行上班打卡"""
        try:
            user_data = await self.load_user_data(user_id)
            
            if not user_data["settings"]["enabled"]:
                return {"success": False, "error": "個人打卡功能未啟用"}
            
            if user_data["active_session"]["is_working"]:
                return {"success": False, "error": "您已經打過卡了"}
            
            clock_in_time = datetime.now()
            status_info = self.calculate_clock_in_status(clock_in_time, user_data["settings"])
            
            work_hours = user_data["settings"]["work_hours"]
            expected_end = clock_in_time + timedelta(hours=work_hours)
            
            # 更新活躍會話
            user_data["active_session"] = {
                "is_working": True,
                "clock_in_time": clock_in_time.isoformat(),
                "clock_in_status": status_info["status"],
                "expected_clock_out": expected_end.isoformat(),
                "guild_id": guild_id,
                "channel_id": channel_id
            }
            
            await self.save_user_data(user_id, user_data)
            
            return {
                "success": True,
                "data": {
                    "clock_in_time": clock_in_time,
                    "status": status_info["status"],
                    "status_color": status_info["status_color"],
                    "late_minutes": status_info["late_minutes"],
                    "expected_end": expected_end,
                    "work_hours": work_hours
                }
            }
            
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"打卡失敗 {user_id}: {e}")
            return {"success": False, "error": "打卡失敗，請稍後再試"}
    
    async def clock_out(self, user_id: int) -> dict:
        """執行下班打卡"""
        try:
            user_data = await self.load_user_data(user_id)
            
            if not user_data["active_session"]["is_working"]:
                return {"success": False, "error": "尚未打卡"}
            
            clock_out_time = datetime.now()
            clock_in_time = datetime.fromisoformat(user_data["active_session"]["clock_in_time"])
            worked_time = clock_out_time - clock_in_time
            worked_hours = worked_time.total_seconds() / 3600
            
            # 記錄到每日記錄
            date_str = clock_out_time.strftime("%Y-%m-%d")
            user_data["records"]["daily"][date_str] = {
                "clock_in": clock_in_time.strftime("%H:%M:%S"),
                "clock_in_status": user_data["active_session"]["clock_in_status"],
                "late_minutes": self.calculate_clock_in_status(clock_in_time, user_data["settings"])["late_minutes"],
                "clock_out": clock_out_time.strftime("%H:%M:%S"),
                "work_hours": round(worked_hours, 2),
                "overtime_hours": max(0, round(worked_hours - user_data["settings"]["work_hours"], 2)),
                "guild_id": user_data["active_session"]["guild_id"]
            }
            
            # 清除活躍會話
            user_data["active_session"] = {
                "is_working": False,
                "clock_in_time": None,
                "clock_in_status": None,
                "expected_clock_out": None,
                "guild_id": None,
                "channel_id": None
            }
            
            await self.save_user_data(user_id, user_data)
            
            return {
                "success": True,
                "data": {
                    "clock_in_time": clock_in_time,
                    "clock_out_time": clock_out_time,
                    "worked_time": worked_time,
                    "worked_hours": worked_hours,
                    "overtime_hours": user_data["records"]["daily"][date_str]["overtime_hours"]
                }
            }
            
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"下班打卡失敗 {user_id}: {e}")
            return {"success": False, "error": "下班打卡失敗，請稍後再試"}
    
    async def get_work_status(self, user_id: int) -> dict:
        """獲取工作狀態"""
        try:
            user_data = await self.load_user_data(user_id)
            
            if not user_data["active_session"]["is_working"]:
                return {"is_working": False}
            
            clock_in_time = datetime.fromisoformat(user_data["active_session"]["clock_in_time"])
            worked_time = datetime.now() - clock_in_time
            expected_end = datetime.fromisoformat(user_data["active_session"]["expected_clock_out"])
            
            return {
                "is_working": True,
                "clock_in_time": clock_in_time,
                "clock_in_status": user_data["active_session"]["clock_in_status"],
                "worked_time": worked_time,
                "worked_hours": int(worked_time.total_seconds() // 3600),
                "worked_minutes": int((worked_time.total_seconds() % 3600) // 60),
                "expected_end": expected_end,
                "settings": user_data["settings"]
            }
            
        except Exception as e:
            BotLogger.error("PersonalClockCore", f"獲取狀態失敗 {user_id}: {e}")
            return {"is_working": False}


# 舊系統 ClockSettings 已移除 - 使用 PersonalClockSettings 替代


class PersonalClockSettings:
    """個人化設定管理"""
    
    def __init__(self, personal_core: PersonalClockCore):
        self.personal_core = personal_core
    
    async def update_user_settings(self, user_id: int, **kwargs) -> dict:
        """更新用戶設定"""
        try:
            user_data = await self.personal_core.load_user_data(user_id)
            
            # 更新設定
            for key, value in kwargs.items():
                if key in user_data["settings"]:
                    user_data["settings"][key] = value
            
            # 如果是首次設定，標記為已完成
            if not user_data["user_info"]["setup_completed"]:
                user_data["user_info"]["setup_completed"] = True
                user_data["settings"]["enabled"] = True
            
            await self.personal_core.save_user_data(user_id, user_data)
            
            return {"success": True, "settings": user_data["settings"]}
            
        except Exception as e:
            BotLogger.error("PersonalClockSettings", f"更新設定失敗 {user_id}: {e}")
            return {"success": False, "error": "設定更新失敗"}
    
    async def get_user_settings(self, user_id: int) -> dict:
        """獲取用戶設定"""
        try:
            user_data = await self.personal_core.load_user_data(user_id)
            return user_data["settings"]
        except Exception as e:
            BotLogger.error("PersonalClockSettings", f"獲取設定失敗 {user_id}: {e}")
            return {}
    
    def validate_settings(self, settings: dict) -> dict:
        """驗證設定值"""
        errors = []
        
        # 驗證上班時間格式
        work_start_time = settings.get("work_start_time", "")
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", work_start_time):
            errors.append("上班時間格式錯誤，請使用 HH:MM 格式")
        
        # 驗證工作時數
        work_hours = settings.get("work_hours", 0)
        try:
            work_hours = float(work_hours)
            if work_hours <= 0 or work_hours > 24:
                errors.append("工作時數必須在 0.1 到 24 小時之間")
        except (ValueError, TypeError):
            errors.append("工作時數必須是數字")
        
        # 驗證彈性時間
        flex_window = settings.get("flex_window_minutes", 30)
        try:
            flex_window = int(flex_window)
            if flex_window < 1 or flex_window > 120:
                errors.append("彈性時間必須在 1 到 120 分鐘之間")
        except (ValueError, TypeError):
            errors.append("彈性時間必須是整數")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "work_hours": work_hours if isinstance(work_hours, (int, float)) else 8.0,
            "flex_window_minutes": flex_window if isinstance(flex_window, int) else 30
        }


# ==================== UI 組件 ====================

class PersonalSetupModal(ui.Modal, title="個人打卡設定"):
    """個人設定Modal"""
    
    def __init__(self, clock_cog):
        super().__init__()
        self.clock_cog = clock_cog
    
    work_start_time = ui.TextInput(
        label="上班時間 (HH:MM 24小時制)",
        placeholder="08:30",
        required=True,
        max_length=5
    )
    
    work_hours = ui.TextInput(
        label="工作時數 (小時)",
        placeholder="8.0",
        required=True,
        max_length=4
    )
    
    flexible_option = ui.TextInput(
        label="彈性打卡 (輸入'是'啟用，留空或'否'關閉)",
        placeholder="否",
        required=False,
        max_length=2
    )
    
    flex_window = ui.TextInput(
        label="彈性時間 (分鐘，僅彈性打卡時有效)",
        placeholder="30",
        required=False,
        max_length=3
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理設定提交"""
        try:
            # 準備設定數據
            settings = {
                "work_start_time": self.work_start_time.value.strip(),
                "work_hours": self.work_hours.value.strip(),
                "flexible_clock_in": self.flexible_option.value.strip().lower() in ["是", "y", "yes", "true"],
                "flex_window_minutes": self.flex_window.value.strip() if self.flex_window.value.strip() else "30"
            }
            
            # 驗證設定
            validation = self.clock_cog.personal_settings.validate_settings(settings)
            
            if not validation["valid"]:
                error_msg = "\n".join([f"• {error}" for error in validation["errors"]])
                embed = discord.Embed(
                    title="❌ 設定驗證失敗",
                    description=f"請修正以下問題：\n\n{error_msg}",
                    color=PERSONAL_CLOCK_COLORS["error"]
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # 更新設定
            result = await self.clock_cog.personal_settings.update_user_settings(
                interaction.user.id,
                work_start_time=settings["work_start_time"],
                work_hours=validation["work_hours"],
                flexible_clock_in=settings["flexible_clock_in"],
                flex_window_minutes=validation["flex_window_minutes"]
            )
            
            if result["success"]:
                # 顯示設定成功的界面
                embed = self.create_setup_success_embed(result["settings"])
                view = PersonalSetupCompleteView(self.clock_cog)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ 設定失敗",
                    description=result.get("error", "未知錯誤"),
                    color=PERSONAL_CLOCK_COLORS["error"]
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            BotLogger.error("PersonalSetupModal", f"設定提交失敗: {e}")
            embed = discord.Embed(
                title="❌ 系統錯誤",
                description="設定提交時發生錯誤，請稍後再試",
                color=PERSONAL_CLOCK_COLORS["error"]
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    def create_setup_success_embed(self, settings: dict) -> discord.Embed:
        """建立設定成功的Embed"""
        embed = discord.Embed(
            title="⚙️ 個人打卡設定完成",
            description="系統將根據您的設定自動提醒打卡",
            color=PERSONAL_CLOCK_COLORS["neutral"],
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🕘 上班時間",
            value=settings["work_start_time"],
            inline=True
        )
        
        embed.add_field(
            name="⏱️ 工作時數",
            value=f"{settings['work_hours']} 小時",
            inline=True
        )
        
        if settings.get("flexible_clock_in"):
            embed.add_field(
                name="🔄 彈性模式",
                value=f"已啟用 ({settings['flex_window_minutes']}分鐘)",
                inline=True
            )
        else:
            embed.add_field(
                name="📌 打卡模式",
                value="定點打卡",
                inline=True
            )
        
        embed.set_footer(text="💡 明日起系統將自動提醒，可使用 /clock settings 修改")
        
        return embed


class PersonalSetupCompleteView(ui.View):
    """設定完成後的操作界面"""
    
    def __init__(self, clock_cog):
        super().__init__(timeout=300)
        self.clock_cog = clock_cog
    
    @ui.button(label="📝 修改設定", style=discord.ButtonStyle.grey)
    async def modify_settings_btn(self, interaction: discord.Interaction, button: ui.Button):
        """修改設定按鈕"""
        modal = PersonalSetupModal(self.clock_cog)
        
        # 預填當前設定
        current_settings = await self.clock_cog.personal_settings.get_user_settings(interaction.user.id)
        modal.work_start_time.default = current_settings.get("work_start_time", "08:30")
        modal.work_hours.default = str(current_settings.get("work_hours", 8.0))
        modal.flexible_option.default = "是" if current_settings.get("flexible_clock_in", False) else "否"
        modal.flex_window.default = str(current_settings.get("flex_window_minutes", 30))
        
        await interaction.response.send_modal(modal)
    
    @ui.button(label="❓ 使用說明", style=discord.ButtonStyle.blurple)
    async def help_btn(self, interaction: discord.Interaction, button: ui.Button):
        """使用說明按鈕"""
        embed = discord.Embed(
            title="❓ 個人打卡系統使用說明",
            color=PERSONAL_CLOCK_COLORS["info"]
        )
        
        embed.add_field(
            name="🔄 自動提醒",
            value="系統會在您設定的上班時間自動彈出打卡界面",
            inline=False
        )
        
        embed.add_field(
            name="📌 定點 vs 彈性模式",
            value="定點：準時打卡，超過1分鐘即遲到\n彈性：有彈性時間窗口，窗口結束後才算遲到",
            inline=False
        )
        
        embed.add_field(
            name="⚡ 緊急指令",
            value="`/clock` - 手動打卡\n`/clock status` - 查看工作狀態",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FlexibleClockInView(ui.View):
    """彈性打卡界面"""
    
    def __init__(self, clock_cog, user_id: int, settings: dict):
        timing = clock_cog.personal_core.get_clock_timing(settings)
        super().__init__(timeout=timing["view_timeout"])
        self.clock_cog = clock_cog
        self.user_id = user_id
        self.settings = settings
        self.timing = timing
    
    @ui.button(label="🟢 立即打卡", style=discord.ButtonStyle.green)
    async def clock_in_btn(self, interaction: discord.Interaction, button: ui.Button):
        """處理打卡按鈕"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是您的打卡界面", ephemeral=True)
            return
        
        result = await self.clock_cog.personal_core.clock_in(
            self.user_id, interaction.guild.id, interaction.channel.id
        )
        
        if result["success"]:
            embed = self.create_clock_in_success_embed(result["data"])
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
    
    @ui.button(label="🔄 重新整理", style=discord.ButtonStyle.grey)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
        """重新整理界面"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是您的打卡界面", ephemeral=True)
            return
        
        embed = self.create_clock_in_reminder_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_clock_in_reminder_embed(self) -> discord.Embed:
        """建立打卡提醒Embed"""
        now = datetime.now()
        
        if self.timing["flex_enabled"]:
            title = "🕘 彈性打卡時間"
            description = "彈性打卡區間內，隨時可以打卡"
            
            # 計算彈性區間
            start_time = self.settings["work_start_time"]
            end_time_parts = self.settings["work_start_time"].split(":")
            end_hour = int(end_time_parts[0])
            end_minute = int(end_time_parts[1]) + self.timing["flex_window"]
            if end_minute >= 60:
                end_hour += 1
                end_minute -= 60
            end_time = f"{end_hour:02d}:{end_minute:02d}"
            
            embed = discord.Embed(
                title=title,
                description=description,
                color=PERSONAL_CLOCK_COLORS["reminder"],
                timestamp=now
            )
            
            embed.add_field(
                name="⏰ 彈性區間",
                value=f"{start_time} - {end_time}",
                inline=True
            )
            
            # 計算剩餘時間
            remaining_minutes = self.timing["flex_window"] - (now.hour * 60 + now.minute - 
                                                             (int(end_time_parts[0]) * 60 + int(end_time_parts[1])))
            if remaining_minutes > 0:
                embed.add_field(
                    name="⏱️ 剩餘時間",
                    value=f"{remaining_minutes} 分鐘",
                    inline=True
                )
            
            embed.set_footer(text=f"💡 超過 {end_time} 將標記為遲到")
        else:
            title = "🕘 上班打卡提醒"
            description = "現在是上班時間，請完成打卡"
            
            embed = discord.Embed(
                title=title,
                description=description,
                color=PERSONAL_CLOCK_COLORS["reminder"],
                timestamp=now
            )
            
            embed.add_field(
                name="⏰ 目標時間",
                value=self.settings["work_start_time"],
                inline=True
            )
            
            # 判斷是否已遲到
            target_time_parts = self.settings["work_start_time"].split(":")
            target_datetime = now.replace(
                hour=int(target_time_parts[0]),
                minute=int(target_time_parts[1]),
                second=0,
                microsecond=0
            )
            
            if now > target_datetime:
                late_minutes = int((now - target_datetime).total_seconds() / 60)
                embed.add_field(
                    name="📊 狀態",
                    value=f"⚠️ 已遲到 {late_minutes}分鐘",
                    inline=True
                )
            else:
                embed.add_field(
                    name="📊 狀態",
                    value="✅ 準時",
                    inline=True
                )
            
            embed.set_footer(text="💡 界面將在 30 分鐘後自動關閉")
        
        embed.add_field(
            name="📅 現在時間",
            value=now.strftime("%H:%M"),
            inline=True
        )
        
        return embed
    
    def create_clock_in_success_embed(self, data: dict) -> discord.Embed:
        """建立打卡成功Embed"""
        embed = discord.Embed(
            title="✅ 打卡成功",
            description="今日上班打卡已完成",
            color=PERSONAL_CLOCK_COLORS["success"],
            timestamp=data["clock_in_time"]
        )
        
        embed.add_field(
            name="🕘 打卡時間",
            value=data["clock_in_time"].strftime("%H:%M"),
            inline=True
        )
        
        if data["late_minutes"] > 0:
            embed.add_field(
                name="📊 狀態",
                value=f"⚠️ 遲到 {data['late_minutes']}分鐘",
                inline=True
            )
        else:
            embed.add_field(
                name="📊 狀態",
                value="✅ 正常",
                inline=True
            )
        
        embed.add_field(
            name="🏁 預計下班",
            value=data["expected_end"].strftime("%H:%M"),
            inline=True
        )
        
        embed.set_footer(text=f"📈 今日工作時數: {data['work_hours']} 小時")
        
        return embed
    
    async def on_timeout(self):
        """處理超時"""
        for item in self.children:
            item.disabled = True


class ClockOutReminderView(ui.View):
    """下班打卡提醒界面"""
    
    def __init__(self, clock_cog, user_id: int):
        super().__init__(timeout=900)  # 15分鐘超時
        self.clock_cog = clock_cog
        self.user_id = user_id
    
    @ui.button(label="🕕 下班打卡", style=discord.ButtonStyle.red)
    async def clock_out_btn(self, interaction: discord.Interaction, button: ui.Button):
        """處理下班打卡"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是您的打卡界面", ephemeral=True)
            return
        
        result = await self.clock_cog.personal_core.clock_out(self.user_id)
        
        if result["success"]:
            embed = self.create_clock_out_success_embed(result["data"])
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
    
    @ui.button(label="📊 查看詳情", style=discord.ButtonStyle.blurple)
    async def view_details_btn(self, interaction: discord.Interaction, button: ui.Button):
        """查看工作詳情"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是您的打卡界面", ephemeral=True)
            return
        
        status = await self.clock_cog.personal_core.get_work_status(self.user_id)
        
        if status["is_working"]:
            embed = create_work_details_embed(status)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ 目前沒有工作記錄", ephemeral=True)
    
    @ui.button(label="⏰ 稍後提醒", style=discord.ButtonStyle.grey)
    async def later_reminder_btn(self, interaction: discord.Interaction, button: ui.Button):
        """稍後提醒"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 這不是您的打卡界面", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⏰ 已設定稍後提醒",
            description="系統將在 15 分鐘後再次提醒您下班打卡",
            color=PERSONAL_CLOCK_COLORS["info"]
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        # 安排稍後提醒（這裡先用簡單的回應，實際可以加入排程）
        # TODO: 實作15分鐘後的提醒機制
    
    def create_clock_out_reminder_embed(self, work_status: dict) -> discord.Embed:
        """建立下班提醒Embed"""
        embed = discord.Embed(
            title="🔔 下班時間到了",
            description="已達到設定工時，可以下班打卡囉！",
            color=PERSONAL_CLOCK_COLORS["warning"],
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🕘 上班時間",
            value=work_status["clock_in_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="⏱️ 已工作",
            value=f"{work_status['worked_hours']}小時 {work_status['worked_minutes']}分鐘",
            inline=True
        )
        
        embed.add_field(
            name="📊 狀態",
            value="✅ 已達標",
            inline=True
        )
        
        if work_status["clock_in_status"] == "遲到":
            embed.add_field(
                name="💡 提醒",
                value="今日遲到打卡，請注意準時上班",
                inline=False
            )
        
        embed.set_footer(text="💡 界面將在 15 分鐘後自動關閉")
        
        return embed
    
    def create_clock_out_success_embed(self, data: dict) -> discord.Embed:
        """建立下班成功Embed"""
        embed = discord.Embed(
            title="👋 下班打卡成功",
            description="今日工作已結束，辛苦了！",
            color=PERSONAL_CLOCK_COLORS["success"],
            timestamp=data["clock_out_time"]
        )
        
        embed.add_field(
            name="🕘 上班時間",
            value=data["clock_in_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="🕕 下班時間",
            value=data["clock_out_time"].strftime("%H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="⏱️ 總工時",
            value=f"{int(data['worked_hours'])}小時 {int((data['worked_hours'] % 1) * 60)}分鐘",
            inline=True
        )
        
        if data["overtime_hours"] > 0:
            embed.add_field(
                name="⏰ 加班時間",
                value=f"{data['overtime_hours']:.1f} 小時",
                inline=False
            )
        
        embed.set_footer(text="📊 記錄已自動保存到個人檔案")
        
        return embed
    
    # create_work_details_embed 已移至獨立工具函數
    
    async def on_timeout(self):
        """處理超時"""
        for item in self.children:
            item.disabled = True


# 舊系統 SmartClockView 已移除


# 舊系統 ClockOutView 已移除


# 舊系統 AdminSetupView 已移除


# ==================== 主要 Cog ====================

class Clock(commands.Cog):
    """個人化打卡系統 - 統一架構"""
    
    def __init__(self, bot):
        self.bot = bot
        # 個人化打卡系統
        self.personal_core = PersonalClockCore()
        self.personal_settings = PersonalClockSettings(self.personal_core)
        self.personal_reminder_task = None
    
    async def cog_load(self):
        """Cog 載入時初始化"""
        # 啟動個人化提醒任務
        if not self.personal_reminder_task:
            self.personal_reminder_task = self.personal_reminder_system.start()
        
        BotLogger.info("Clock", "個人化打卡系統已啟動")
    
    def cog_unload(self):
        """Cog 卸載時清理"""
        if self.personal_reminder_task:
            self.personal_reminder_task.cancel()
    
    # ===== 個人化指令系統 =====
    
    @commands.hybrid_command(name="pclock")
    async def personal_clock_setup(self, ctx):
        """個人化打卡設定"""
        modal = PersonalSetupModal(self)
        
        # 如果已有設定，預填當前值
        current_settings = await self.personal_settings.get_user_settings(ctx.author.id)
        if current_settings:
            modal.work_start_time.default = current_settings.get("work_start_time", "08:30")
            modal.work_hours.default = str(current_settings.get("work_hours", 8.0))
            modal.flexible_option.default = "是" if current_settings.get("flexible_clock_in", False) else "否"
            modal.flex_window.default = str(current_settings.get("flex_window_minutes", 30))
        
        await ctx.interaction.response.send_modal(modal)
    
    @commands.hybrid_command(name="pstatus")
    async def personal_status(self, ctx):
        """查看個人工作狀態"""
        status = await self.personal_core.get_work_status(ctx.author.id)
        
        if not status["is_working"]:
            # 檢查是否已設定
            user_data = await self.personal_core.load_user_data(ctx.author.id)
            if not user_data["user_info"]["setup_completed"]:
                embed = discord.Embed(
                    title="🔧 尚未設定個人打卡",
                    description="請先使用 `/pclock` 指令進行個人設定",
                    color=PERSONAL_CLOCK_COLORS["neutral"]
                )
            else:
                embed = discord.Embed(
                    title="📋 目前沒有打卡記錄",
                    description="系統會在您設定的時間自動提醒打卡",
                    color=PERSONAL_CLOCK_COLORS["info"]
                )
        else:
            # 顯示詳細狀態
            embed = create_work_details_embed(status)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="pclock_manual")
    async def personal_manual_clock(self, ctx):
        """手動打卡（緊急使用）"""
        user_data = await self.personal_core.load_user_data(ctx.author.id)
        
        if not user_data["user_info"]["setup_completed"]:
            embed = discord.Embed(
                title="🔧 尚未設定個人打卡",
                description="請先使用 `/pclock` 指令進行個人設定",
                color=PERSONAL_CLOCK_COLORS["neutral"]
            )
            await ctx.send(embed=embed)
            return
        
        if not user_data["active_session"]["is_working"]:
            # 執行打卡
            result = await self.personal_core.clock_in(ctx.author.id, ctx.guild.id, ctx.channel.id)
            
            if result["success"]:
                embed = FlexibleClockInView(self, ctx.author.id, user_data["settings"]).create_clock_in_success_embed(result["data"])
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ {result['error']}")
        else:
            # 顯示下班選項
            status = await self.personal_core.get_work_status(ctx.author.id)
            embed = ClockOutReminderView(self, ctx.author.id).create_clock_out_reminder_embed(status)
            view = ClockOutReminderView(self, ctx.author.id)
            await ctx.send(embed=embed, view=view)
    
    # ===== 向後相容指令 =====
    
    @commands.hybrid_command(name="clock", aliases=["打卡"])
    async def smart_clock_compat(self, ctx):
        """
        智能打卡 - 向後相容指令（調用新系統）
        請使用 /pclock 進行個人設定，使用 /pclock_manual 手動打卡
        """
        embed = discord.Embed(
            title="🔄 打卡系統已升級",
            description="舊版打卡系統已整合為個人化系統",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🆕 新指令",
            value="`/pclock` - 個人設定\n`/pclock_manual` - 手動打卡\n`/pstatus` - 查看狀態",
            inline=False
        )
        
        embed.add_field(
            name="✨ 新功能",
            value="• 完全個人化設定\n• 彈性打卡模式\n• 自動提醒系統\n• 詳細工時記錄",
            inline=False
        )
        
        embed.set_footer(text="💡 請先使用 /pclock 完成個人設定")
        
        await ctx.send(embed=embed)
    
    # 舊系統內部方法已移除
    
    # 舊系統互動處理方法已移除
    
    # 舊系統定時提醒已移除 - 使用個人化提醒系統
    
    # ===== 個人化定時提醒系統 =====
    
    @tasks.loop(minutes=1)
    async def personal_reminder_system(self):
        """個人化打卡提醒檢查"""
        try:
            now = datetime.now(TAIPEI_TZ)
            current_time = now.time()
            
            # 遍歷所有用戶的個人設定
            if not os.path.exists(self.personal_core.users_dir):
                return
            
            for filename in os.listdir(self.personal_core.users_dir):
                if not filename.startswith("clock_user_") or not filename.endswith(".json"):
                    continue
                
                try:
                    # 提取用戶ID
                    user_id_str = filename.replace("clock_user_", "").replace(".json", "")
                    user_id = int(user_id_str)
                    
                    # 載入用戶數據
                    user_data = await self.personal_core.load_user_data(user_id)
                    
                    # 檢查是否啟用且已完成設定
                    if not user_data["settings"]["enabled"] or not user_data["user_info"]["setup_completed"]:
                        continue
                    
                    # 檢查是否已在工作
                    if user_data["active_session"]["is_working"]:
                        # 檢查是否該下班了
                        await self._check_clock_out_reminder(user_id, user_data)
                        continue
                    
                    # 檢查是否該上班提醒
                    await self._check_clock_in_reminder(user_id, user_data, current_time)
                    
                except Exception as e:
                    BotLogger.error("PersonalReminder", f"處理用戶 {filename} 失敗: {e}")
                    continue
                    
        except Exception as e:
            BotLogger.error("PersonalReminder", f"個人提醒系統錯誤: {e}")
    
    async def _check_clock_in_reminder(self, user_id: int, user_data: dict, current_time: time):
        """檢查上班提醒"""
        try:
            settings = user_data["settings"]
            timing = self.personal_core.get_clock_timing(settings)
            
            # 檢查是否到了提醒時間
            if (current_time.hour == timing["reminder_time"].hour and 
                current_time.minute == timing["reminder_time"].minute):
                
                # 找到用戶並發送提醒
                user = self.bot.get_user(user_id)
                if not user:
                    return
                
                # 找到用戶的最後活動伺服器（簡化版本，可以改進）
                guild = None
                channel = None
                
                for g in self.bot.guilds:
                    member = g.get_member(user_id)
                    if member:
                        # 尋找合適的頻道
                        channel = discord.utils.find(
                            lambda c: c.name in ['general', '一般', '打卡', 'clock'] and
                                     isinstance(c, discord.TextChannel) and
                                     c.permissions_for(member).send_messages,
                            g.channels
                        )
                        if channel:
                            guild = g
                            break
                
                if channel:
                    await self._send_personal_clock_in_reminder(channel, user_id, settings)
                    BotLogger.info("PersonalReminder", f"發送個人打卡提醒給 {user.name}")
                
        except Exception as e:
            BotLogger.error("PersonalReminder", f"檢查上班提醒失敗 {user_id}: {e}")
    
    async def _check_clock_out_reminder(self, user_id: int, user_data: dict):
        """檢查下班提醒"""
        try:
            if not user_data["active_session"]["is_working"]:
                return
            
            clock_in_time = datetime.fromisoformat(user_data["active_session"]["clock_in_time"])
            work_hours = user_data["settings"]["work_hours"]
            expected_end = clock_in_time + timedelta(hours=work_hours)
            
            # 檢查是否到了下班時間（擴大到30分鐘窗口，增加防重複機制）
            now = datetime.now()
            
            # 檢查是否已經發送過提醒（避免重複提醒）
            last_reminder = user_data["active_session"].get("last_clock_out_reminder")
            if last_reminder:
                last_reminder_time = datetime.fromisoformat(last_reminder)
                # 如果30分鐘內已提醒過，跳過
                if now - last_reminder_time < timedelta(minutes=30):
                    return
            
            # 擴大提醒窗口：到達下班時間後30分鐘內都會提醒
            if now >= expected_end and now <= expected_end + timedelta(minutes=30):
                
                # 找到用戶
                user = self.bot.get_user(user_id)
                if not user:
                    return
                
                # 找到用戶的工作頻道
                guild = self.bot.get_guild(user_data["active_session"]["guild_id"])
                if not guild:
                    return
                
                channel = guild.get_channel(user_data["active_session"]["channel_id"])
                if not channel:
                    # 尋找其他合適頻道
                    channel = discord.utils.find(
                        lambda c: c.name in ['general', '一般', '打卡', 'clock'] and
                                 isinstance(c, discord.TextChannel),
                        guild.channels
                    )
                
                if channel:
                    await self._send_personal_clock_out_reminder(channel, user_id)
                    
                    # 記錄提醒時間，避免重複提醒
                    user_data["active_session"]["last_clock_out_reminder"] = now.isoformat()
                    await self.personal_core.save_user_data(user_id, user_data)
                    
                    BotLogger.info("PersonalReminder", f"發送個人下班提醒給 {user.name}")
                
        except Exception as e:
            BotLogger.error("PersonalReminder", f"檢查下班提醒失敗 {user_id}: {e}")
    
    async def _send_personal_clock_in_reminder(self, channel, user_id: int, settings: dict):
        """發送個人上班提醒"""
        try:
            view = FlexibleClockInView(self, user_id, settings)
            embed = view.create_clock_in_reminder_embed()
            
            await channel.send(f"<@{user_id}>", embed=embed, view=view)
            
        except Exception as e:
            BotLogger.error("PersonalReminder", f"發送上班提醒失敗 {user_id}: {e}")
    
    async def _send_personal_clock_out_reminder(self, channel, user_id: int):
        """發送個人下班提醒"""
        try:
            status = await self.personal_core.get_work_status(user_id)
            if not status["is_working"]:
                return
            
            view = ClockOutReminderView(self, user_id)
            embed = view.create_clock_out_reminder_embed(status)
            
            await channel.send(f"<@{user_id}>", embed=embed, view=view)
            
        except Exception as e:
            BotLogger.error("PersonalReminder", f"發送下班提醒失敗 {user_id}: {e}")


async def setup(bot):
    await bot.add_cog(Clock(bot))