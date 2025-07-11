import asyncio
import logging
import sys
import os
from typing import Optional

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twitchio.ext import commands
from shared.config.modular_config import config
from utils.logger import TwitchLogger

# 初始化日誌系統
TwitchLogger.initialize(config.get_twitch_config('LOG_LEVEL', 'INFO'), config.get_twitch_config('LOG_TO_FILE', True))
logger = logging.getLogger(__name__)

class TwitchBot(commands.Bot):
    """Niibot Twitch 實現"""
    
    def __init__(self):
        # 確保配置有效
        if not config.get_twitch_config('BOT_TOKEN'):
            logger.error("配置驗證失敗，缺少 BOT_TOKEN")
            sys.exit(1)
        
        # 取得配置值 (TwitchIO 2.x 只需要基本參數)
        bot_token = config.get_twitch_config('BOT_TOKEN')
        
        # 處理頻道名稱格式
        channels_config = config.get_twitch_config('INITIAL_CHANNELS', [])
        if isinstance(channels_config, str):
            # 如果是字串，轉換為列表
            initial_channels = [channels_config] if channels_config else []
        else:
            initial_channels = channels_config
            
        TwitchLogger.info("INIT", f"頻道配置: {channels_config}, 處理後: {initial_channels}")
        
        # 檢查 Token 格式
        if bot_token and bot_token.startswith('oauth:'):
            TwitchLogger.info("TOKEN", f"Token 格式正確: oauth:***")
        else:
            TwitchLogger.error("TOKEN", "Bot Token 格式錯誤或為空！")
        
        # TwitchIO 2.x 簡化初始化 (類似示例B、C)
        super().__init__(
            token=bot_token,
            prefix=config.get_twitch_config('COMMAND_PREFIX', '?'),
            initial_channels=initial_channels
        )
        
        TwitchLogger.info("INIT", f"Twitch Bot 初始化完成 (TwitchIO 2.9.1)")
        
        # 初始化基礎資料路徑
        self.data_path = config.get_twitch_config('DATA_PATH', 'data')
        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)
        
        # 冷卻機制
        self.user_cooldowns = {}
        
        initial_channels = config.get_twitch_config('INITIAL_CHANNELS', [])
        TwitchLogger.system_event("機器人初始化", f"將加入頻道: {initial_channels}")
    
    async def event_ready(self):
        """Bot 準備就緒事件"""
        bot_nick = config.get_twitch_config('BOT_NICK', 'niibot')
        TwitchLogger.system_event("Bot準備就緒", f"用戶: {bot_nick}")
        
        # TwitchIO 2.x 連接狀態檢查
        try:
            # 檢查頻道連接（TwitchIO 2.x 使用 connected_channels）
            if hasattr(self, 'connected_channels') and self.connected_channels:
                channel_names = [getattr(ch, 'name', str(ch)) for ch in self.connected_channels]
                TwitchLogger.system_event("已加入頻道", f"{channel_names}")
                TwitchLogger.info("CONNECTION", f"成功連接到 {len(self.connected_channels)} 個頻道")
            else:
                TwitchLogger.info("CONNECTION", "等待連接到頻道...")
                
            # 檢查Bot暱稱
            if hasattr(self, 'nick') and self.nick:
                TwitchLogger.info("AUTH", f"Bot暱稱: {self.nick}")
            else:
                TwitchLogger.info("AUTH", "使用配置的Bot暱稱")
                
        except Exception as e:
            TwitchLogger.error("CONNECTION", f"連接檢查失敗: {e}")
        
        # 初始化必要的資料檔案
        await self.init_data_files()
        
        TwitchLogger.system_event("Bot初始化完成", "所有功能已載入")
    
    async def event_message(self, message):
        """處理所有訊息"""
        # 忽略 bot 自己的訊息
        if message.echo:
            return
        
        # 詳細的訊息除錯
        TwitchLogger.info("MESSAGE", f"收到訊息 - 頻道: {message.channel.name}, 用戶: {message.author.name}, 內容: '{message.content}'")
        
        # 檢查是否為指令
        prefix = config.get_twitch_config('COMMAND_PREFIX', '!')
        if message.content.startswith(prefix):
            TwitchLogger.info("COMMAND", f"檢測到指令 - 前綴: '{prefix}', 訊息: '{message.content}'")
        
        # 處理指令
        try:
            await self.handle_commands(message)
        except Exception as e:
            TwitchLogger.error("COMMAND_HANDLER", f"處理指令時發生錯誤: {e}")
    
    async def event_command_error(self, context, error):
        """處理指令錯誤"""
        TwitchLogger.error("COMMAND_ERROR", f"[{context.channel.name}] {context.author.name}: {error}")
        
        if isinstance(error, commands.CommandNotFound):
            # 指令不存在時不回應，避免干擾聊天
            pass
        elif isinstance(error, commands.MissingRequiredArgument):
            await context.send(f"❌ 缺少必要參數")
        else:
            await context.send(f"❌ 指令執行錯誤")
    
    async def init_data_files(self):
        """初始化必要的資料檔案"""
        try:
            from utils.data_manager import SimpleDataManager
            data_manager = SimpleDataManager(self.data_path)
            
            # 確保基本資料檔案存在
            files_to_init = [
                ("eat.json", {
                    "categories": {
                        "主餐": ["漢堡", "意麵", "拉麵", "炸雞", "披薩"],
                        "點心": ["蛋糕", "餅乾", "布丁", "冰淇淋"],
                        "飲料": ["咖啡", "茶", "果汁", "汽水"]
                    },
                    "metadata": {"version": "1.0", "platform": "twitch"}
                }),
                ("draw_history.json", {
                    "draws": [],
                    "stats": {"total_draws": 0, "platforms": {"twitch": 0}},
                    "metadata": {"version": "1.0", "platform": "twitch"}
                })
            ]
            
            for filename, default_data in files_to_init:
                if not data_manager.file_exists(filename):
                    await data_manager.write_json(filename, default_data)
                    TwitchLogger.info("INIT", f"初始化資料檔案: {filename}")
            
            TwitchLogger.system_event("資料檔案初始化完成", f"共 {len(files_to_init)} 個檔案")
            
        except Exception as e:
            TwitchLogger.error("INIT", f"初始化資料檔案失敗: {e}")
    
    def check_permissions(self, user_name: str, required_level: str = "user") -> bool:
        """檢查用戶權限"""
        user_name = user_name.lower()
        
        if required_level == "admin":
            admin_users = config.get_twitch_config('ADMIN_USERS', [])
            return user_name in [admin.lower() for admin in admin_users]
        elif required_level == "mod":
            moderator_users = config.get_twitch_config('MODERATOR_USERS', [])
            admin_users = config.get_twitch_config('ADMIN_USERS', [])
            return (user_name in [mod.lower() for mod in moderator_users] or
                    user_name in [admin.lower() for admin in admin_users])
        else:  # user level
            return True
    
    def check_cooldown(self, user_name: str, command: str, cooldown_seconds: int) -> bool:
        """檢查冷卻時間"""
        import time
        current_time = time.time()
        
        user_key = f"{user_name}_{command}"
        
        if user_key in self.user_cooldowns:
            time_diff = current_time - self.user_cooldowns[user_key]
            if time_diff < cooldown_seconds:
                return False
        
        self.user_cooldowns[user_key] = current_time
        return True
    
    # === 核心指令 ===
    
    @commands.command(name='test')
    async def test_command(self, ctx):
        """測試指令"""
        try:
            TwitchLogger.info("COMMAND", f"執行 test 指令 - 用戶: {ctx.author.name}, 頻道: {ctx.channel.name}")
            channel_name = ctx.channel.name if ctx.channel else "未知"
            response = f"✅ Niibot Twitch 正常運作！頻道: {channel_name}"
            await ctx.send(response)
            TwitchLogger.command_log(channel_name, ctx.author.name, "test", "success")
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 test 指令失敗: {e}")
            try:
                await ctx.send("❌ 測試指令執行失敗")
            except:
                pass
    
    @commands.command(name='help')
    async def help_command(self, ctx):
        """顯示幫助訊息"""
        try:
            prefix = config.get_twitch_config('COMMAND_PREFIX')
            help_text = f"""🤖 Niibot Twitch 指令說明：
{prefix}test - 測試bot狀態
{prefix}help - 顯示此說明
{prefix}ping - Pong!
{prefix}info - 顯示bot資訊

🍽️ 用餐推薦：
{prefix}eat [分類] - 隨機推薦食物
{prefix}eat_categories - 顯示餐點分類

🎲 抽獎功能：
{prefix}draw 選項1 選項2 ... - 隨機抽獎
{prefix}draw 選項1*權重1 選項2*權重2 - 權重抽獎
{prefix}draw_stats - 抽獎統計
{prefix}draw_history - 抽獎記錄"""
            
            await ctx.send(help_text)
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "help", "success")
        
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 help 指令失敗: {e}")
            await ctx.send("❌ 幫助指令執行失敗")
    
    @commands.command(name='ping')
    async def ping_command(self, ctx):
        """Ping 指令"""
        try:
            await ctx.send("🏓 Pong!")
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "ping", "success")
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 ping 指令失敗: {e}")
    
    @commands.command(name='info')
    async def info_command(self, ctx):
        """顯示機器人資訊"""
        try:
            info_text = f"""📊 Niibot Twitch 資訊：
🏷️ 版本: 2.0 (原生設計)
🤖 平台: Twitch
⚙️ 前綴: {config.get_twitch_config('COMMAND_PREFIX')}
📂 功能: 用餐推薦、系統指令
🔧 開發者: yPinn"""
            
            await ctx.send(info_text)
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "info", "success")
        
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 info 指令失敗: {e}")
            await ctx.send("❌ 資訊指令執行失敗")

    # === 用餐推薦功能 ===
    
    @commands.command(name='eat')
    async def eat_command(self, ctx, category: str = None):
        """隨機推薦食物"""
        try:
            # 檢查冷卻
            if not self.check_cooldown(ctx.author.name, "eat", 
                                     config.get_twitch_config('EAT_COOLDOWN', 30)):
                return
            
            from utils.data_manager import SimpleDataManager
            data_manager = SimpleDataManager(self.data_path)
            
            eat_data = await data_manager.read_json("eat.json")
            categories = eat_data.get("categories", {})
            
            if category and category in categories:
                # 指定分類
                items = categories[category]
                if items:
                    import random
                    choice = random.choice(items)
                    await ctx.send(f"🍽️ 推薦 {category}：{choice}")
                else:
                    await ctx.send(f"❌ {category} 分類是空的")
            else:
                # 隨機分類
                if categories:
                    import random
                    all_items = []
                    for cat_items in categories.values():
                        all_items.extend(cat_items)
                    
                    if all_items:
                        choice = random.choice(all_items)
                        await ctx.send(f"🍽️ 今天吃：{choice}")
                    else:
                        await ctx.send("❌ 沒有可用的餐點")
                else:
                    await ctx.send("❌ 沒有餐點資料")
            
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "eat", "success")
            
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 eat 指令失敗: {e}")
            await ctx.send("❌ 用餐推薦失敗")

    @commands.command(name='eat_categories')
    async def eat_categories_command(self, ctx):
        """顯示餐點分類"""
        try:
            from utils.data_manager import SimpleDataManager
            data_manager = SimpleDataManager(self.data_path)
            
            eat_data = await data_manager.read_json("eat.json")
            categories = eat_data.get("categories", {})
            
            if categories:
                category_list = ", ".join(categories.keys())
                await ctx.send(f"🍽️ 可用分類：{category_list}")
            else:
                await ctx.send("❌ 沒有餐點分類")
            
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "eat_categories", "success")
            
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 eat_categories 指令失敗: {e}")
            await ctx.send("❌ 無法顯示分類")

    # === 抽獎功能 ===

    async def _get_draw_data(self):
        """獲取抽獎資料"""
        from utils.data_manager import SimpleDataManager
        data_manager = SimpleDataManager(self.data_path)
        
        default_data = {
            "draws": [],
            "stats": {
                "total_draws": 0,
                "platforms": {"twitch": 0}
            },
            "metadata": {
                "version": "1.0",
                "platform": "twitch"
            }
        }
        return await data_manager.read_json("draw_history.json", default_data)

    async def _save_draw_record(self, options, result, user, channel):
        """儲存抽獎記錄"""
        try:
            from utils.data_manager import SimpleDataManager
            from datetime import datetime
            
            data_manager = SimpleDataManager(self.data_path)
            
            def update_func(data):
                # 新增抽獎記錄
                draw_record = {
                    "id": f"draw_{len(data.get('draws', [])) + 1}",
                    "timestamp": datetime.now().isoformat(),
                    "platform": "twitch",
                    "channel": channel,
                    "user": user,
                    "options": list(options),
                    "result": result,
                    "type": "simple"
                }
                
                if "draws" not in data:
                    data["draws"] = []
                data["draws"].append(draw_record)
                
                # 更新統計
                if "stats" not in data:
                    data["stats"] = {"total_draws": 0, "platforms": {"twitch": 0}}
                
                data["stats"]["total_draws"] = data["stats"].get("total_draws", 0) + 1
                if "platforms" not in data["stats"]:
                    data["stats"]["platforms"] = {"twitch": 0}
                data["stats"]["platforms"]["twitch"] = data["stats"]["platforms"].get("twitch", 0) + 1
                
                # 只保留最近100筆記錄
                if len(data["draws"]) > 100:
                    data["draws"] = data["draws"][-100:]
                
                return data
            
            await data_manager.update_json("draw_history.json", update_func)
            TwitchLogger.info("DRAW", f"儲存抽獎記錄: {user} 在 {channel}")
            
        except Exception as e:
            TwitchLogger.error("DRAW", f"儲存抽獎記錄失敗: {e}")

    def _parse_weighted_options(self, args):
        """解析帶權重的選項"""
        weighted_options = []
        
        for arg in args:
            if '*' in arg:
                # 帶權重的選項，格式：選項*權重
                parts = arg.split('*')
                if len(parts) == 2:
                    option = parts[0].strip()
                    try:
                        weight = int(parts[1].strip())
                        if weight > 0:
                            weighted_options.append((option, weight))
                        else:
                            weighted_options.append((option, 1))
                    except ValueError:
                        weighted_options.append((option, 1))
                else:
                    weighted_options.append((arg, 1))
            else:
                # 無權重的選項
                weighted_options.append((arg, 1))
        
        return weighted_options

    def _weighted_choice(self, weighted_options):
        """根據權重進行選擇"""
        import random
        # 建立選項池
        choices = []
        for option, weight in weighted_options:
            choices.extend([option] * weight)
        
        return random.choice(choices)

    @commands.command(name='draw')
    async def draw_command(self, ctx, *args):
        """抽獎指令"""
        try:
            # 檢查冷卻
            if not self.check_cooldown(ctx.author.name, "draw", 
                                     config.get_twitch_config('DRAW_COOLDOWN', 10)):
                return
            
            if not args:
                prefix = config.get_twitch_config('COMMAND_PREFIX')
                await ctx.send(f"❌ 請提供選項！用法: {prefix}draw 選項1 選項2 選項3")
                return
            
            if len(args) < 2:
                await ctx.send("❌ 至少需要 2 個選項才能抽獎")
                return
            
            if len(args) > 20:
                await ctx.send("❌ 選項數量不能超過 20 個")
                return
            
            # 解析選項（檢查是否有權重）
            has_weights = any('*' in arg for arg in args)
            
            if has_weights:
                # 權重抽獎
                weighted_options = self._parse_weighted_options(args)
                result = self._weighted_choice(weighted_options)
                
                # 顯示權重資訊
                weight_info = []
                for option, weight in weighted_options:
                    weight_info.append(f"{option}({weight})")
                
                response = f"🎲 權重抽獎結果：**{result}**\n選項: {', '.join(weight_info)}"
            else:
                # 一般抽獎
                import random
                result = random.choice(args)
                response = f"🎲 抽獎結果：**{result}**\n選項: {', '.join(args)}"
            
            await ctx.send(response)
            
            # 儲存抽獎記錄
            await self._save_draw_record(args, result, ctx.author.name, ctx.channel.name)
            
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, f"draw {len(args)}選項", "success")
        
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 draw 指令失敗: {e}")
            await ctx.send("❌ 抽獎執行失敗，請稍後再試")

    @commands.command(name='draw_stats')
    async def draw_stats_command(self, ctx):
        """顯示抽獎統計"""
        try:
            draw_data = await self._get_draw_data()
            stats = draw_data.get("stats", {})
            
            total_draws = stats.get("total_draws", 0)
            twitch_draws = stats.get("platforms", {}).get("twitch", 0)
            
            response = f"📊 抽獎統計：\n總抽獎次數: {total_draws}\nTwitch 平台: {twitch_draws}"
            
            await ctx.send(response)
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "draw_stats", "success")
        
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 draw_stats 指令失敗: {e}")
            await ctx.send("❌ 無法獲取統計資料")

    @commands.command(name='draw_history')
    async def draw_history_command(self, ctx):
        """顯示最近的抽獎記錄"""
        try:
            draw_data = await self._get_draw_data()
            draws = draw_data.get("draws", [])
            
            if not draws:
                await ctx.send("📜 目前沒有抽獎記錄")
                return
            
            # 顯示最近5筆記錄
            recent_draws = draws[-5:]
            
            response = "📜 最近的抽獎記錄：\n"
            for draw in reversed(recent_draws):
                user = draw.get("user", "未知")
                result = draw.get("result", "未知")
                options_count = len(draw.get("options", []))
                timestamp = draw.get("timestamp", "")
                
                # 簡化時間顯示
                if timestamp:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        time_str = dt.strftime("%m-%d %H:%M")
                    except:
                        time_str = "未知時間"
                else:
                    time_str = "未知時間"
                
                response += f"• {time_str} {user}: {result} ({options_count}選項)\n"
            
            await ctx.send(response)
            TwitchLogger.command_log(ctx.channel.name, ctx.author.name, "draw_history", "success")
        
        except Exception as e:
            TwitchLogger.error("COMMAND", f"執行 draw_history 指令失敗: {e}")
            await ctx.send("❌ 無法獲取歷史記錄")

async def main():
    """主函數"""
    # 確保日誌目錄存在
    os.makedirs("../logs", exist_ok=True)
    
    # 創建並啟動 bot
    bot = TwitchBot()
    
    try:
        TwitchLogger.system_event("開始啟動 TwitchBot")
        await bot.start()
    except KeyboardInterrupt:
        TwitchLogger.system_event("收到中斷信號，正在關閉 bot")
    except Exception as e:
        TwitchLogger.error("MAIN", f"Bot 運行錯誤: {e}")
    finally:
        TwitchLogger.system_event("TwitchBot 已關閉")

if __name__ == "__main__":
    asyncio.run(main())