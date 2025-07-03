import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import util
from utils.logger import BotLogger
from utils.config_manager import config


class TwitterMonitor(commands.Cog):
    """X (Twitter) 帳號監控系統

    監控指定 X 帳號的新貼文並發送到 Discord 頻道
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = "twitter_monitor.json"
        self.processed_posts_file = "twitter_processed.json"

        # 配置資料
        self.monitor_config = {}
        self.processed_posts = set()

        # API 設定
        self.twitter_bearer_token = None
        self.google_translate_key = None

        # HTTP 會話
        self.session: Optional[aiohttp.ClientSession] = None

        BotLogger.info("TwitterMonitor", "Twitter 監控系統初始化")

    async def cog_load(self):
        """Cog 載入時執行"""
        await self.load_data()
        await self.setup_http_session()
        await self.load_api_keys()

        # 啟動監控任務
        if self.monitor_config.get("enabled", False) and self.twitter_bearer_token:
            self.monitor_task.start()
            BotLogger.info("TwitterMonitor", "監控任務已啟動")
        else:
            BotLogger.warning("TwitterMonitor", "監控任務未啟動 - 請檢查配置和API金鑰")

    async def cog_unload(self):
        """Cog 卸載時執行"""
        if self.monitor_task.is_running():
            self.monitor_task.cancel()

        if self.session and not self.session.closed:
            await self.session.close()

        await self.save_data()
        BotLogger.info("TwitterMonitor", "Twitter 監控系統已卸載")

    async def load_data(self):
        """載入配置和已處理貼文資料"""
        try:
            # 載入監控配置
            self.monitor_config = await util.read_json(
                util.get_data_file_path(self.config_file)
            ) or {
                "enabled": False,
                "target_username": "",
                "target_user_id": "",
                "discord_channel_id": 0,
                "check_interval": 1800,  # 30分鐘
                "last_check": None,
                "translation_enabled": False
            }

            # 載入已處理貼文ID
            processed_data = await util.read_json(
                util.get_data_file_path(self.processed_posts_file)
            ) or []
            self.processed_posts = set(processed_data)

            BotLogger.info("TwitterMonitor",
                           f"載入配置完成 - 已處理貼文: {len(self.processed_posts)}")

        except Exception as e:
            BotLogger.error("TwitterMonitor", "載入資料失敗", e)
            # 使用預設配置
            self.monitor_config = {
                "enabled": False,
                "target_username": "",
                "target_user_id": "",
                "discord_channel_id": 0,
                "check_interval": 1800,
                "last_check": None,
                "translation_enabled": False
            }
            self.processed_posts = set()

    async def save_data(self):
        """儲存配置和已處理貼文資料"""
        try:
            # 儲存監控配置
            await util.write_json(
                util.get_data_file_path(self.config_file),
                self.monitor_config
            )

            # 儲存已處理貼文ID（只保留最近1000個）
            processed_list = list(self.processed_posts)[-1000:]
            await util.write_json(
                util.get_data_file_path(self.processed_posts_file),
                processed_list
            )

            BotLogger.debug("TwitterMonitor", "資料儲存完成")

        except Exception as e:
            BotLogger.error("TwitterMonitor", "儲存資料失敗", e)

    async def setup_http_session(self):
        """設定 HTTP 會話"""
        if not self.session or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={"User-Agent": "Niibot Twitter Monitor 1.0"}
            )

    async def load_api_keys(self):
        """載入 API 金鑰"""
        # 從環境變數或配置檔案載入
        self.twitter_bearer_token = config.get("TWITTER_BEARER_TOKEN")
        self.google_translate_key = config.get("GOOGLE_TRANSLATE_API_KEY")

        if not self.twitter_bearer_token:
            BotLogger.warning("TwitterMonitor", "Twitter Bearer Token 未設定")
        else:
            BotLogger.info("TwitterMonitor", "Twitter Bearer Token 已載入")

        if not self.google_translate_key:
            BotLogger.warning("TwitterMonitor",
                              "Google Translate API Key 未設定 - 將跳過翻譯功能")
        else:
            BotLogger.info("TwitterMonitor", "Google Translate API Key 已載入")

    @tasks.loop(seconds=60)  # 每分鐘檢查一次
    async def monitor_task(self):
        """主要監控任務"""
        try:
            if not self.monitor_config.get("enabled", False):
                BotLogger.debug("TwitterMonitor", "監控已停用，跳過檢查")
                return

            # 檢查是否到了檢查時間
            last_check = self.monitor_config.get("last_check")
            check_interval = self.monitor_config.get("check_interval", 300)

            now = datetime.now()
            if last_check:
                try:
                    last_check_time = datetime.fromisoformat(last_check)
                    time_diff = now - last_check_time
                    if time_diff.total_seconds() < check_interval:
                        BotLogger.debug(
                            "TwitterMonitor", f"尚未到檢查時間，剩餘 {check_interval - time_diff.total_seconds():.0f} 秒")
                        return
                except ValueError:
                    BotLogger.warning("TwitterMonitor",
                                      "last_check 時間格式錯誤，重置檢查時間")

            BotLogger.info("TwitterMonitor", "開始檢查新貼文...")

            # 執行檢查
            await self.check_new_posts()

            # 更新最後檢查時間
            self.monitor_config["last_check"] = now.isoformat()
            await self.save_data()

        except Exception as e:
            BotLogger.error("TwitterMonitor", "監控任務執行失敗", e)

    async def check_new_posts(self):
        """檢查新貼文"""
        try:
            if not self.twitter_bearer_token:
                BotLogger.warning("TwitterMonitor",
                                  "Twitter Bearer Token 未設定，無法檢查貼文")
                return

            user_id = self.monitor_config.get("target_user_id")
            username = self.monitor_config.get("target_username")
            if not user_id:
                BotLogger.warning("TwitterMonitor", "目標用戶 ID 未設定")
                return

            BotLogger.info("TwitterMonitor",
                           f"檢查 @{username} (ID: {user_id}) 的新貼文...")

            # 取得用戶最新貼文
            tweets = await self.get_user_tweets(user_id, count=10)  # 增加到10篇
            if not tweets:
                BotLogger.warning("TwitterMonitor", "未取得到任何貼文")
                return

            BotLogger.info("TwitterMonitor", f"取得了 {len(tweets)} 篇貼文")

            # 處理新貼文
            new_posts_count = 0
            for tweet in reversed(tweets):  # 從舊到新處理
                tweet_id = tweet.get("id")
                if tweet_id:
                    if tweet_id not in self.processed_posts:
                        BotLogger.info("TwitterMonitor", f"發現新貼文: {tweet_id}")
                        success = await self.process_new_tweet(tweet)
                        if success:
                            self.processed_posts.add(tweet_id)
                            new_posts_count += 1
                    else:
                        BotLogger.debug("TwitterMonitor",
                                        f"貼文已處理過: {tweet_id}")

            if new_posts_count > 0:
                BotLogger.info("TwitterMonitor",
                               f"成功處理了 {new_posts_count} 個新貼文")
                await self.save_data()
            else:
                BotLogger.info("TwitterMonitor", "沒有新貼文需要處理")

        except Exception as e:
            BotLogger.error("TwitterMonitor", "檢查新貼文失敗", e)

    async def get_user_tweets(self, user_id: str, count: int = 5) -> List[Dict]:
        """取得指定用戶的最新貼文"""
        try:
            if not self.session:
                await self.setup_http_session()

            url = f"https://api.twitter.com/2/users/{user_id}/tweets"
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}",
                "Content-Type": "application/json"
            }

            params = {
                "max_results": min(count, 100),
                "tweet.fields": "created_at,author_id,text,attachments,public_metrics",
                "expansions": "attachments.media_keys",
                "media.fields": "url,preview_image_url,type",
                "exclude": "retweets,replies"  # 排除轉推和回覆
            }

            BotLogger.debug("TwitterMonitor", f"發送 Twitter API 請求: {url}")

            async with self.session.get(url, headers=headers, params=params) as response:
                response_text = await response.text()
                BotLogger.debug("TwitterMonitor",
                                f"Twitter API 響應狀態: {response.status}")

                if response.status == 200:
                    data = await response.json()
                    tweets = data.get("data", [])

                    if not tweets:
                        BotLogger.warning("TwitterMonitor", "API 回應中沒有貼文資料")
                        return []

                    # 處理媒體資訊
                    media = {m["media_key"]: m for m in data.get(
                        "includes", {}).get("media", [])}

                    # 將媒體資訊附加到貼文
                    for tweet in tweets:
                        if "attachments" in tweet and "media_keys" in tweet["attachments"]:
                            tweet["media"] = [
                                media.get(key) for key in tweet["attachments"]["media_keys"]
                                if key in media
                            ]

                    BotLogger.info("TwitterMonitor", f"成功取得 {len(tweets)} 篇貼文")
                    return tweets

                elif response.status == 401:
                    BotLogger.error("TwitterMonitor",
                                    "Twitter API 認證失敗 - 請檢查 Bearer Token")
                    return []
                elif response.status == 404:
                    BotLogger.error("TwitterMonitor", f"找不到用戶 ID: {user_id}")
                    return []
                elif response.status == 429:
                    # 實施指數退避 - 延長下次檢查時間
                    BotLogger.error("TwitterMonitor",
                                    "Twitter API 請求頻率限制 - 延長檢查間隔")
                    # 暫時延長檢查間隔到 1 小時
                    current_interval = self.monitor_config.get("check_interval", 1800)
                    self.monitor_config["check_interval"] = max(current_interval * 2, 3600)
                    await self.save_data()
                    return []
                else:
                    BotLogger.error(
                        "TwitterMonitor", f"Twitter API 錯誤: {response.status} - {response_text[:200]}")
                    return []

        except Exception as e:
            BotLogger.error("TwitterMonitor", "取得貼文失敗", e)
            return []

    async def translate_text(self, text: str, target_lang: str = "zh-TW") -> str:
        """翻譯文字"""
        try:
            if not self.google_translate_key or not text.strip():
                return text

            if not self.session:
                await self.setup_http_session()

            url = "https://translation.googleapis.com/language/translate/v2"
            data = {
                "q": text,
                "target": target_lang,
                "key": self.google_translate_key
            }

            async with self.session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    translated = result["data"]["translations"][0]["translatedText"]
                    return translated
                else:
                    BotLogger.warning("TwitterMonitor",
                                      f"翻譯 API 錯誤: {response.status}")
                    return text

        except Exception as e:
            BotLogger.error("TwitterMonitor", "翻譯失敗", e)
            return text

    async def process_new_tweet(self, tweet: Dict) -> bool:
        """處理新貼文"""
        try:
            channel_id = self.monitor_config.get("discord_channel_id")
            if not channel_id:
                BotLogger.error("TwitterMonitor", "Discord 頻道 ID 未設定")
                return False

            channel = self.bot.get_channel(channel_id)
            if not channel:
                BotLogger.error("TwitterMonitor",
                                f"找不到 Discord 頻道: {channel_id}")
                return False

            # 建立 embed
            embed = await self.create_tweet_embed(tweet)
            if not embed:
                BotLogger.error("TwitterMonitor", "建立 embed 失敗")
                return False

            # 發送到 Discord
            await channel.send(embed=embed)
            tweet_id = tweet.get('id')
            BotLogger.info("TwitterMonitor", f"成功發送新貼文到 Discord: {tweet_id}")
            return True

        except Exception as e:
            BotLogger.error("TwitterMonitor", "處理新貼文失敗", e)
            return False

    async def create_tweet_embed(self, tweet: Dict) -> Optional[discord.Embed]:
        """建立貼文 embed"""
        try:
            tweet_id = tweet.get("id")
            text = tweet.get("text", "")
            created_at = tweet.get("created_at")
            username = self.monitor_config.get("target_username", "Unknown")

            # 建立 embed
            embed = discord.Embed(
                title=f"🐦 來自 @{username} 的新貼文",
                color=0x1DA1F2,  # Twitter 藍
                timestamp=datetime.fromisoformat(created_at.replace(
                    "Z", "+00:00")) if created_at else discord.utils.utcnow()
            )

            # 貼文內容
            if text:
                embed.add_field(
                    name="📝 內容",
                    value=text[:1024],  # Discord embed 欄位限制
                    inline=False
                )

            # 翻譯功能（可選）
            if self.monitor_config.get("translation_enabled", False) and text and self.google_translate_key:
                try:
                    translated_text = await self.translate_text(text)
                    if translated_text and translated_text != text:
                        embed.add_field(
                            name="🔤 繁體中文翻譯",
                            value=translated_text[:1024],
                            inline=False
                        )
                except Exception as e:
                    BotLogger.warning("TwitterMonitor", f"翻譯失敗: {e}")

            # 貼文連結
            if tweet_id:
                tweet_url = f"https://twitter.com/i/status/{tweet_id}"
                embed.add_field(
                    name="🔗 原始連結",
                    value=f"[查看原貼文]({tweet_url})",
                    inline=True
                )

            # 互動統計
            metrics = tweet.get("public_metrics", {})
            if metrics:
                stats = []
                if metrics.get("like_count"):
                    stats.append(f"❤️ {metrics['like_count']}")
                if metrics.get("retweet_count"):
                    stats.append(f"🔄 {metrics['retweet_count']}")
                if metrics.get("reply_count"):
                    stats.append(f"💬 {metrics['reply_count']}")

                if stats:
                    embed.add_field(
                        name="📊 互動統計",
                        value=" | ".join(stats),
                        inline=True
                    )

            # 處理媒體
            media_list = tweet.get("media", [])
            if media_list:
                # 設定第一張圖片為 embed 圖片
                first_image = None
                media_links = []

                for media in media_list:
                    if media and media.get("type") == "photo":
                        media_url = media.get("url")
                        if media_url:
                            if not first_image:
                                first_image = media_url
                            media_links.append(f"[圖片]({media_url})")
                    elif media and media.get("type") == "video":
                        preview_url = media.get("preview_image_url")
                        if preview_url:
                            media_links.append(f"[影片預覽]({preview_url})")

                if first_image:
                    embed.set_image(url=first_image)

                if media_links:
                    embed.add_field(
                        name="🖼️ 媒體內容",
                        value=" | ".join(media_links),
                        inline=False
                    )

            embed.set_footer(
                text="Niibot Twitter Monitor",
                icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
            )

            return embed

        except Exception as e:
            BotLogger.error("TwitterMonitor", "建立 embed 失敗", e)
            return None

    @app_commands.command(name="twitter_add", description="新增 Twitter 帳號監控")
    @app_commands.describe(
        username="要監控的 Twitter 用戶名（不含 @）",
        channel="發送貼文的 Discord 頻道",
        interval="檢查間隔（秒，建議1800秒以上）",
        enable_translation="是否啟用翻譯功能（需要 Google API）"
    )
    async def add_twitter_monitor(
        self,
        interaction: discord.Interaction,
        username: str,
        channel: discord.TextChannel,
        interval: int = 1800,
        enable_translation: bool = False
    ):
        """設定 Twitter 監控"""
        try:
            await interaction.response.defer()

            if interval < 60:
                await interaction.followup.send("❌ 檢查間隔不能少於 60 秒")
                return

            if not self.twitter_bearer_token:
                await interaction.followup.send("❌ Twitter API 金鑰未設定，請聯繫管理員")
                return

            # 檢查翻譯功能設定
            if enable_translation and not self.google_translate_key:
                await interaction.followup.send("⚠️ 翻譯功能需要 Google Translate API Key，將停用翻譯功能")
                enable_translation = False

            # 取得用戶 ID
            user_id = await self.get_user_id_by_username(username)
            if not user_id:
                await interaction.followup.send(f"❌ 找不到用戶 @{username}")
                return

            # 更新配置
            self.monitor_config.update({
                "enabled": True,
                "target_username": username,
                "target_user_id": user_id,
                "discord_channel_id": channel.id,
                "check_interval": interval,
                "translation_enabled": enable_translation
            })

            await self.save_data()

            # 啟動監控任務
            if not self.monitor_task.is_running():
                self.monitor_task.start()

            embed = discord.Embed(
                title="✅ Twitter 監控新增完成",
                color=0x00ff00
            )
            embed.add_field(name="監控用戶", value=f"@{username}", inline=True)
            embed.add_field(name="目標頻道", value=channel.mention, inline=True)
            embed.add_field(name="檢查間隔", value=f"{interval} 秒", inline=True)
            translation_status = "已啟用" if enable_translation else "已停用"
            embed.add_field(name="翻譯功能", value=translation_status, inline=True)

            await interaction.followup.send(embed=embed)

            BotLogger.command_used(
                "twitter_add",
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                f"用戶: @{username}, 頻道: {channel.id}, 翻譯: {enable_translation}"
            )

        except Exception as e:
            BotLogger.error("TwitterMonitor", "新增監控失敗", e)
            await interaction.followup.send("❌ 新增失敗，請稍後再試")

    async def get_user_id_by_username(self, username: str) -> Optional[str]:
        """根據用戶名取得用戶 ID"""
        try:
            if not self.session:
                await self.setup_http_session()

            url = f"https://api.twitter.com/2/users/by/username/{username}"
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}",
                "Content-Type": "application/json"
            }

            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("id")
                else:
                    BotLogger.error("TwitterMonitor",
                                    f"取得用戶 ID 失敗: {response.status}")
                    return None

        except Exception as e:
            BotLogger.error("TwitterMonitor", "取得用戶 ID 失敗", e)
            return None

    @app_commands.command(name="twitter_remove", description="清空 Twitter 監控設定")
    async def remove_twitter_monitor(self, interaction: discord.Interaction):
        """清空監控設定"""
        try:
            # 檢查是否有監控設定
            username = self.monitor_config.get("target_username", "")
            if not username:
                await interaction.response.send_message("❌ 目前沒有設定任何監控", ephemeral=True)
                return

            # 停止監控任務
            if self.monitor_task.is_running():
                self.monitor_task.cancel()

            # 清空配置
            self.monitor_config.update({
                "enabled": False,
                "target_username": "",
                "target_user_id": "",
                "discord_channel_id": 0,
                "last_check": None,
                "translation_enabled": False
            })

            # 清空已處理貼文記錄
            self.processed_posts.clear()

            # 儲存變更
            await self.save_data()

            embed = discord.Embed(
                title="🗑️ Twitter 監控已清空",
                description=f"已移除對 @{username} 的監控設定",
                color=0xff9900
            )
            embed.add_field(
                name="📋 清空內容", 
                value="• 監控目標\n• 頻道設定\n• 已處理貼文記錄", 
                inline=False
            )
            embed.set_footer(text="使用 /twitter_add 重新設定監控")

            await interaction.response.send_message(embed=embed)

            BotLogger.command_used(
                "twitter_remove",
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                f"移除用戶: @{username}"
            )

        except Exception as e:
            BotLogger.error("TwitterMonitor", "清空監控失敗", e)
            await interaction.response.send_message("❌ 清空失敗，請稍後再試", ephemeral=True)

    @app_commands.command(name="twitter_status", description="查看 Twitter 監控狀態")
    async def twitter_status(self, interaction: discord.Interaction):
        """查看監控狀態"""
        try:
            embed = discord.Embed(
                title="🐦 Twitter 監控狀態",
                color=0x1DA1F2
            )

            # 基本狀態
            enabled = self.monitor_config.get("enabled", False)
            embed.add_field(
                name="監控狀態",
                value="🟢 運行中" if enabled else "🔴 已停止",
                inline=True
            )

            # 監控目標
            username = self.monitor_config.get("target_username", "未設定")
            embed.add_field(name="監控用戶", value=f"@{username}", inline=True)

            # 目標頻道
            channel_id = self.monitor_config.get("discord_channel_id")
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                channel_name = channel.mention if channel else f"頻道 ID: {channel_id}"
            else:
                channel_name = "未設定"
            embed.add_field(name="目標頻道", value=channel_name, inline=True)

            # 檢查間隔
            interval = self.monitor_config.get("check_interval", 300)
            embed.add_field(name="檢查間隔", value=f"{interval} 秒", inline=True)

            # 翻譯狀態
            translation = "已啟用" if self.monitor_config.get(
                "translation_enabled", False) else "已停用"
            embed.add_field(name="翻譯功能", value=translation, inline=True)

            # 最後檢查時間
            last_check = self.monitor_config.get("last_check")
            if last_check:
                last_check_time = datetime.fromisoformat(last_check)
                time_diff = datetime.now() - last_check_time
                if time_diff.seconds < 60:
                    last_check_str = f"{time_diff.seconds} 秒前"
                elif time_diff.seconds < 3600:
                    last_check_str = f"{time_diff.seconds // 60} 分鐘前"
                else:
                    last_check_str = f"{time_diff.seconds // 3600} 小時前"
            else:
                last_check_str = "從未檢查"
            embed.add_field(name="最後檢查", value=last_check_str, inline=True)

            # 已處理貼文數量
            embed.add_field(
                name="已處理貼文",
                value=f"{len(self.processed_posts)} 個",
                inline=True
            )

            # API 狀態
            api_status = []
            if self.twitter_bearer_token:
                api_status.append("✅ Twitter API")
            else:
                api_status.append("❌ Twitter API")

            if self.google_translate_key:
                api_status.append("✅ 翻譯 API")
            else:
                api_status.append("❌ 翻譯 API")

            embed.add_field(
                name="API 狀態",
                value="\n".join(api_status),
                inline=True
            )

            embed.set_footer(text="使用 /twitter_add 來新增監控\n翻譯功能默認關閉，可在設定時開啟")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            BotLogger.error("TwitterMonitor", "查看狀態失敗", e)
            await interaction.response.send_message("❌ 查看狀態失敗", ephemeral=True)

    @app_commands.command(name="twitter_start", description="啟動 Twitter 監控")
    async def start_twitter_monitor(self, interaction: discord.Interaction):
        """啟動監控"""
        try:
            # 檢查是否有監控設定
            username = self.monitor_config.get("target_username", "")
            if not username:
                await interaction.response.send_message("❌ 請先使用 /twitter_add 設定監控目標", ephemeral=True)
                return

            # 檢查是否已經啟動
            if self.monitor_config.get("enabled", False):
                await interaction.response.send_message("⚠️ 監控已經在運行中", ephemeral=True)
                return

            # 檢查 API 金鑰
            if not self.twitter_bearer_token:
                await interaction.response.send_message("❌ Twitter API 金鑰未設定，請聯繫管理員", ephemeral=True)
                return

            # 啟動監控
            self.monitor_config["enabled"] = True
            await self.save_data()

            if not self.monitor_task.is_running():
                self.monitor_task.start()

            embed = discord.Embed(
                title="▶️ Twitter 監控已啟動",
                description=f"開始監控 @{username} 的新貼文",
                color=0x00ff00
            )
            channel_id = self.monitor_config.get("discord_channel_id")
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    embed.add_field(name="發送頻道", value=channel.mention, inline=True)

            await interaction.response.send_message(embed=embed)

            BotLogger.command_used(
                "twitter_start",
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                f"啟動監控: @{username}"
            )

        except Exception as e:
            BotLogger.error("TwitterMonitor", "啟動監控失敗", e)
            await interaction.response.send_message("❌ 啟動失敗，請稍後再試", ephemeral=True)

    @app_commands.command(name="twitter_stop", description="停止 Twitter 監控")
    async def stop_twitter_monitor(self, interaction: discord.Interaction):
        """停止監控"""
        try:
            # 檢查是否有監控設定
            username = self.monitor_config.get("target_username", "")
            if not username:
                await interaction.response.send_message("❌ 目前沒有設定任何監控", ephemeral=True)
                return

            # 檢查是否已經停止
            if not self.monitor_config.get("enabled", False):
                await interaction.response.send_message("⚠️ 監控已經停止", ephemeral=True)
                return

            # 停止監控
            self.monitor_config["enabled"] = False
            await self.save_data()

            if self.monitor_task.is_running():
                self.monitor_task.cancel()

            embed = discord.Embed(
                title="⏹️ Twitter 監控已停止",
                description=f"已停止監控 @{username}",
                color=0xff0000
            )
            embed.add_field(
                name="💡 提示", 
                value="使用 /twitter_start 重新啟動監控\n使用 /twitter_remove 清空設定", 
                inline=False
            )

            await interaction.response.send_message(embed=embed)

            BotLogger.command_used(
                "twitter_stop",
                interaction.user.id,
                interaction.guild.id if interaction.guild else 0,
                f"停止監控: @{username}"
            )

        except Exception as e:
            BotLogger.error("TwitterMonitor", "停止監控失敗", e)
            await interaction.response.send_message("❌ 停止失敗，請稍後再試", ephemeral=True)


async def setup(bot: commands.Bot):
    """設定 Cog"""
    await bot.add_cog(TwitterMonitor(bot))
    BotLogger.system_event("Cog載入", "TwitterMonitor cog 已成功載入")
