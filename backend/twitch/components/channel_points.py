import logging
import os
import twitchio
from twitchio.ext import commands
from typing import TYPE_CHECKING, Optional

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

    def _generate_oauth_url(self) -> str:
        """生成統一的 OAuth 授權 URL。

        Returns:
            完整的 OAuth 授權 URL
        """
        client_id = os.getenv("CLIENT_ID", "")
        if not client_id:
            raise ValueError("CLIENT_ID 未設定")

        # 從環境變數讀取 redirect URI，預設為 localhost
        redirect_uri = os.getenv(
            "OAUTH_REDIRECT_URI", "http://localhost:4343/oauth/callback"
        )

        scopes = [
            "user:bot",
            "channel:bot",
            "user:write:chat",
            "user:manage:whispers",
            "channel:read:redemptions",
            "channel:manage:vips",
            "channel:read:subscriptions",
            "channel:read:hype_train",
            "channel:read:polls",
            "channel:read:predictions",
            "bits:read",
        ]

        from urllib.parse import quote

        scope_string = "+".join(scope.replace(":", "%3A") for scope in scopes)
        encoded_redirect_uri = quote(redirect_uri, safe="")

        oauth_url = (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_string}"
        )

        return oauth_url

    # ==================== EventSub 事件監聽器 ====================

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
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
            f"[DEBUG] event_custom_redemption_add 觸發！Payload 類型: {type(payload)}"
        )

        user_name = payload.user.name
        reward_title = payload.reward.title
        reward_cost = payload.reward.cost
        user_input = payload.user_input or ""
        redemption_id = payload.id

        # 記錄兌換事件
        LOGGER.info(
            f"[Channel Points] {user_name} 兌換「{reward_title}」"
            f"(花費 {reward_cost} 點數，頻道: {payload.broadcaster.name})"
        )
        if user_input:
            LOGGER.debug(f"[Channel Points] 用戶輸入: {user_input}")

        # 根據獎勵標題執行不同的動作
        # 您可以在這裡添加自訂邏輯
        await self._handle_redemption(payload)

    @commands.Component.listener()
    async def event_custom_redemption_update(
        self,
        payload: twitchio.ChannelPointsRedemptionUpdate,
    ) -> None:
        """當兌換狀態更新時觸發（例如：標記為完成或取消）。"""
        LOGGER.debug(
            f"[Channel Points] 兌換狀態更新: "
            f"{payload.user.name} 的「{payload.reward.title}」-> {payload.status}"
        )

    # ==================== 兌換處理邏輯 ====================

    async def _handle_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """處理兌換事件並執行對應動作。

        您可以根據獎勵標題執行不同的邏輯。
        以下是一些範例，您可以根據需求修改。
        """
        reward_title = payload.reward.title.lower()
        user_name = payload.user.name
        user_input = payload.user_input or ""

        # 🤖 Niibot 獎勵 - 發送 OAuth 授權連結
        if "niibot" in reward_title and user_name:
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
                LOGGER.warning("[Action] 點歌獎勵缺少歌曲資訊")

        # VIP 獎勵 - 自動授予 VIP 身分
        elif "vip" in reward_title:
            LOGGER.info(f"[Action] {user_name} 兌換了 VIP 獎勵")
            await self._handle_vip_redemption(payload, user_name)

        # 範例 4: 自訂訊息
        elif "訊息" in reward_title or "message" in reward_title:
            if user_input:
                LOGGER.info(f"[Action] {user_name} 的自訂訊息: {user_input}")
                # 可以在聊天室顯示訊息

        # 預設處理
        else:
            LOGGER.info(
                f"[Action] 收到兌換「{payload.reward.title}」，但沒有設定對應的處理邏輯"
            )

    async def _handle_vip_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: Optional[str],
    ) -> None:
        """處理 VIP 獎勵兌換 - 自動授予 VIP 身分。

        當用戶兌換 VIP 獎勵時：
        1. 使用 Twitch API 授予該用戶 VIP 身分
        2. 在聊天室發送確認訊息

        注意：需要 channel:manage:vips scope
        """
        try:
            # 獲取 broadcaster 的 PartialUser
            broadcaster = payload.broadcaster

            # 授予 VIP 身分
            # 需要 broadcaster 的 token 和接收者的 user_id
            await broadcaster.add_vip(user=payload.user)

            # 在聊天室發送確認訊息
            success_message = f"恭喜 @{user_name} 成為尊榮的 VIP 大人 👑"
            try:
                await broadcaster.send_message(
                    message=success_message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )
                LOGGER.info(f"[VIP] 已授予 {user_name} VIP 身分並發送確認訊息")
            except Exception as e:
                LOGGER.warning(f"[VIP] 已授予 VIP 但發送訊息失敗: {e}")

        except Exception as e:
            error_str = str(e)

            # 處理不同的錯誤情況
            if "422" in error_str:
                if "moderator" in error_str.lower():
                    # 用戶已經是 Moderator
                    LOGGER.warning(
                        f"[VIP] {user_name} 已經是 Moderator，無法授予 VIP（Twitch 限制）"
                    )
                    error_message = f"@{user_name} 你已經是 Moderator 了！"
                elif "already a vip" in error_str.lower():
                    # 用戶已經是 VIP
                    LOGGER.info(f"[VIP] {user_name} 已經是 VIP")
                    error_message = f"@{user_name} 你已經是 VIP 了！👑"
                else:
                    # 其他 422 錯誤
                    LOGGER.error(f"[VIP] 授予 VIP 身分失敗 (422): {e}")
                    error_message = f"@{user_name} ⚠️ VIP 授予失敗，請聯繫管理員"
            else:
                # 其他錯誤
                LOGGER.error(f"[VIP] 授予 VIP 身分失敗: {e}")
                error_message = f"@{user_name} ⚠️ VIP 授予失敗，請聯繫管理員"

            # 發送錯誤訊息
            try:
                await payload.broadcaster.send_message(
                    message=error_message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )
            except Exception:
                pass  # 如果連錯誤訊息都發送失敗，就只記錄在 log

    async def _handle_niibot_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理 Niibot 獎勵兌換 - 自動發送 OAuth 授權連結。

        當用戶兌換 Niibot 獎勵時：
        1. 在聊天室發送公開確認訊息
        2. 透過私訊發送 OAuth 授權連結（保護隱私）
        """
        try:
            # 生成 OAuth 授權 URL（使用統一的方法）
            try:
                oauth_url = self._generate_oauth_url()
            except ValueError as e:
                LOGGER.error(f"[Niibot] 生成 OAuth URL 失敗: {e}")
                return

            # 獲取 broadcaster 的 PartialUser 物件
            broadcaster = payload.broadcaster

            # 1. 在聊天室發送公開確認訊息
            public_message = (
                f"@{user_name} 已將授權連結發送至你的 Twitch 私訊 "
            )
            try:
                await broadcaster.send_message(
                    message=public_message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )
                LOGGER.info(
                    f"[Niibot] 已在 {broadcaster.name} 聊天室發送確認訊息給 {user_name}"
                )
            except Exception as e:
                LOGGER.warning(f"[Niibot] 發送公開訊息失敗: {e}")

            # 2. 透過私訊發送 OAuth 連結（更私密安全）
            whisper_message = f"請點擊以下連結授權 Niibot 存取你的頻道：\n{oauth_url}"
            try:
                # 使用 TwitchIO 3 的正確方法：從 Bot 發送 whisper 給用戶
                # 創建 Bot 的 PartialUser，然後發送給接收者
                bot_user = self.bot.create_partialuser(user_id=self.bot.bot_id)
                await bot_user.send_whisper(
                    to_user=payload.user,  # 接收者
                    message=whisper_message,
                )
                LOGGER.info(
                    f"[Niibot] 已發送私訊給 {user_name} (ID: {payload.user.id})"
                )
            except Exception as e:
                LOGGER.error(f"[Niibot] 發送私訊失敗: {e}")
                # 如果私訊失敗，fallback 到聊天室發送提示訊息（不包含 URL，避免超過 500 字元）
                fallback_message = (
                    f"@{user_name} ⚠️ 私訊發送失敗，請聯繫 Bot Owner 獲取授權連結"
                )
                try:
                    await broadcaster.send_message(
                        message=fallback_message,
                        sender=self.bot.bot_id,
                        token_for=self.bot.bot_id,
                    )
                    LOGGER.info(
                        f"[Niibot] 已 fallback 到聊天室提示 {user_name} 使用命令"
                    )
                except Exception as fallback_error:
                    LOGGER.error(f"[Niibot] Fallback 發送也失敗: {fallback_error}")

        except Exception as e:
            LOGGER.error(f"[Niibot] 處理兌換時發生錯誤: {e}")

    # ==================== 資訊查詢命令 ====================

    @commands.command()
    async def niibot(self, ctx: commands.Context[Bot]) -> None:
        """提供 Niibot OAuth 授權連結（僅限 Bot Owner 使用）。

        Usage: !niibot

        此命令僅供 Bot Owner 使用，用於控管授權用戶數量。
        """
        try:
            # 檢查權限：僅 Bot Owner 可使用
            if not ctx.message:
                LOGGER.warning("[Niibot] 無法獲取訊息資訊")
                return

            chatter = ctx.message.chatter

            # 檢查是否為 Bot Owner
            if chatter.id != self.bot.owner_id:
                LOGGER.warning(
                    f"[Niibot] {chatter.name} (ID: {chatter.id}) 嘗試使用命令但不是 Bot Owner"
                )
                await ctx.reply(f"@{chatter.name} ⚠️ 此命令僅供 Bot Owner 使用")
                return

            # 生成 OAuth 授權 URL（使用統一的方法）
            try:
                oauth_url = self._generate_oauth_url()
            except ValueError:
                await ctx.reply("❌ OAuth 設定錯誤，請聯繫管理員")
                return

            await ctx.reply(
                f"@{ctx.author.name} 請點擊以下連結授權 Niibot 存取你的頻道：{oauth_url}"
            )
            LOGGER.info(f"[Niibot] 已回覆 OAuth 連結給 {ctx.author.name}")

        except Exception as e:
            LOGGER.error(f"[Niibot] 命令執行錯誤: {e}")
            await ctx.reply("❌ 生成授權連結時發生錯誤")

    @commands.command()
    async def redemptions(self, ctx: commands.Context["Bot"]) -> None:
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
