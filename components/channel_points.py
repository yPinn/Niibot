import logging
import os
import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger("ChannelPoints")


class ChannelPointsComponent(commands.Component):
    """Channel Points (頻道點數) 兌換監聽組件。

    功能：
    - 監聽點數兌換事件
    - 根據獎勵標題自動執行對應動作
    - 記錄所有兌換活動

    不包含：
    - 獎勵的創建、更新、刪除（請使用 Twitch 後台管理）
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==================== EventSub 事件監聽器 ====================

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd
    ) -> None:
        """當用戶兌換 Channel Points 獎勵時觸發。

        Args:
            payload: 兌換資料，包含：
                - user: 兌換用戶資訊
                - reward: 獎勵資訊
                - user_input: 用戶輸入內容（如果獎勵需要輸入）
                - id: 兌換 ID
                - broadcaster: 頻道資訊
                - status: 兌換狀態 (UNFULFILLED, FULFILLED, CANCELED)
        """
        LOGGER.debug(
            f"[DEBUG] event_custom_redemption_add 觸發！Payload 類型: {type(payload)}")

        user_name = payload.user.name
        reward_title = payload.reward.title
        reward_cost = payload.reward.cost
        user_input = payload.user_input or ""
        redemption_id = payload.id

        # 記錄兌換事件
        LOGGER.info(
            f"[Channel Points] {user_name} 在頻道 {payload.broadcaster.name} "
            f"兌換了「{reward_title}」(花費 {reward_cost} 點數)"
        )
        if user_input:
            LOGGER.info(f"[Channel Points] 用戶輸入: {user_input}")

        # 根據獎勵標題執行不同的動作
        # 您可以在這裡添加自訂邏輯
        await self._handle_redemption(payload)

    @commands.Component.listener()
    async def event_custom_redemption_update(
        self,
        payload: twitchio.ChannelPointsRedemptionUpdate
    ) -> None:
        """當兌換狀態更新時觸發（例如：標記為完成或取消）。"""
        LOGGER.info(
            f"[Channel Points] 兌換狀態更新: "
            f"{payload.user.name} 的「{payload.reward.title}」-> {payload.status}"
        )

    # ==================== 兌換處理邏輯 ====================

    async def _handle_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd
    ) -> None:
        """處理兌換事件並執行對應動作。

        您可以根據獎勵標題執行不同的邏輯。
        以下是一些範例，您可以根據需求修改。
        """
        reward_title = payload.reward.title.lower()
        user_name = payload.user.name
        user_input = payload.user_input or ""

        # 🤖 Niibot 獎勵 - 發送 OAuth 授權連結
        if "niibot" in reward_title:
            await self._handle_niibot_redemption(payload, user_name)

        # 範例 1: 打招呼獎勵
        elif "打招呼" in reward_title or "say hi" in reward_title:
            # 可以在這裡發送聊天訊息（需要獲取頻道物件）
            LOGGER.info(f"[Action] 執行打招呼動作給 {user_name}")
            # 實作範例：
            # channel = self.bot.get_channel(payload.broadcaster_user_id)
            # if channel:
            #     await channel.send(f"感謝 {user_name} 的兌換！嗨~")

        # 範例 2: 點歌獎勵
        elif "點歌" in reward_title or "song request" in reward_title:
            if user_input:
                LOGGER.info(f"[Action] {user_name} 點歌: {user_input}")
                # 可以在這裡整合點歌系統
            else:
                LOGGER.warning(f"[Action] 點歌獎勵缺少歌曲資訊")

        # 範例 3: VIP 獎勵
        elif "vip" in reward_title:
            LOGGER.info(f"[Action] {user_name} 兌換了 VIP")
            # 可以在這裡執行授予 VIP 的邏輯

        # 範例 4: 自訂訊息
        elif "訊息" in reward_title or "message" in reward_title:
            if user_input:
                LOGGER.info(f"[Action] {user_name} 的自訂訊息: {user_input}")
                # 可以在聊天室顯示訊息

        # 預設處理
        else:
            LOGGER.info(
                f"[Action] 收到兌換「{payload.reward.title}」，"
                f"但沒有設定對應的處理邏輯"
            )

    async def _handle_niibot_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str
    ) -> None:
        """處理 Niibot 獎勵兌換 - 自動發送 OAuth 授權連結。

        當用戶兌換 Niibot 獎勵時，自動調用內部方法發送 OAuth 授權連結到聊天室。
        """
        try:
            # 獲取 CLIENT_ID
            client_id = os.getenv("CLIENT_ID", "")
            if not client_id:
                LOGGER.error("[Niibot] CLIENT_ID 未設定，無法生成 OAuth 連結")
                return

            # 生成 OAuth 授權 URL
            oauth_url = (
                f"https://id.twitch.tv/oauth2/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback"
                f"&response_type=code"
                f"&scope=channel%3Abot+channel%3Amanage%3Aredemptions+channel%3Aread%3Aredemptions"
                f"+moderator%3Aread%3Afollowers+channel%3Aread%3Asubscriptions"
                f"+moderator%3Amanage%3Achat_messages+moderator%3Aread%3Achatters"
                f"+channel%3Aread%3Ahype_train+channel%3Aread%3Apolls"
                f"+channel%3Aread%3Apredictions+bits%3Aread"
            )

            # 直接調用 _send_oauth_link 發送訊息
            await self._send_oauth_link(
                broadcaster_id=payload.broadcaster.id,
                user_name=user_name,
                oauth_url=oauth_url
            )

        except Exception as e:
            LOGGER.error(f"[Niibot] 處理兌換時發生錯誤: {e}")

    async def _send_oauth_link(
        self,
        broadcaster_id: str,
        user_name: str,
        oauth_url: str
    ) -> None:
        """發送 OAuth 連結到聊天室（內部方法）。"""
        try:
            message = f"@{user_name} 請點擊以下連結授權 Niibot 存取你的頻道：{oauth_url}"

            # 使用 Helix API 發送訊息
            url = "https://api.twitch.tv/helix/chat/messages"
            payload_data = {
                "broadcaster_id": broadcaster_id,
                "sender_id": self.bot.bot_id,
                "message": message
            }

            import json as json_module
            response = await self.bot._http.request(
                "POST",
                url,
                body=json_module.dumps(payload_data),
                headers={"Content-Type": "application/json"}
            )

            if response.status == 200:
                LOGGER.info(f"[Niibot] 已發送 OAuth 連結給 {user_name}")
            else:
                error_text = await response.text()
                LOGGER.error(
                    f"[Niibot] 發送訊息失敗 (HTTP {response.status}): {error_text}"
                )

        except Exception as e:
            LOGGER.error(f"[Niibot] 發送訊息時發生錯誤: {e}")

    # ==================== 資訊查詢命令 ====================

    @commands.command()
    async def niibot(self, ctx: commands.Context[Bot]) -> None:
        """提供 Niibot OAuth 授權連結（僅限管理員和頻道主使用）。

        Usage: !niibot
        """
        try:
            # 檢查權限：僅管理員或頻道主可使用
            if not (ctx.author.is_mod or ctx.author.is_broadcaster):
                LOGGER.warning(f"[Niibot] {ctx.author.name} 嘗試使用命令但權限不足")
                return

            # 獲取 CLIENT_ID
            client_id = os.getenv("CLIENT_ID", "")
            if not client_id:
                await ctx.reply("❌ OAuth 設定錯誤，請聯繫管理員")
                return

            # 生成 OAuth 授權 URL
            oauth_url = (
                f"https://id.twitch.tv/oauth2/authorize"
                f"?client_id={client_id}"
                f"&redirect_uri=http%3A%2F%2Flocalhost%3A4343%2Foauth%2Fcallback"
                f"&response_type=code"
                f"&scope=channel%3Abot+channel%3Amanage%3Aredemptions+channel%3Aread%3Aredemptions"
                f"+moderator%3Aread%3Afollowers+channel%3Aread%3Asubscriptions"
                f"+moderator%3Amanage%3Achat_messages+moderator%3Aread%3Achatters"
                f"+channel%3Aread%3Ahype_train+channel%3Aread%3Apolls"
                f"+channel%3Aread%3Apredictions+bits%3Aread"
            )

            await ctx.reply(
                f"@{ctx.author.name} 請點擊以下連結授權 Niibot 存取你的頻道：{oauth_url}"
            )
            LOGGER.info(f"[Niibot] 已回覆 OAuth 連結給 {ctx.author.name}")

        except Exception as e:
            LOGGER.error(f"[Niibot] 命令執行錯誤: {e}")
            await ctx.reply("❌ 生成授權連結時發生錯誤")

    @commands.command()
    async def redemptions(self, ctx: commands.Context[Bot]) -> None:
        """顯示 Channel Points 兌換功能的說明。

        Usage: !redemptions
        """
        await ctx.reply(
            "📊 Channel Points 兌換系統已啟用！"
            "Bot 會自動監聽並記錄所有兌換事件。"
            "請使用 Twitch 後台管理獎勵。"
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(ChannelPointsComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
