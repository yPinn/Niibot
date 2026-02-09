import logging
from typing import TYPE_CHECKING

import twitchio
from twitchio.ext import commands

from core.config import get_settings
from shared.repositories.command_config import RedemptionConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger("ChannelPoints")


class ChannelPointsComponent(commands.Component):
    """Channel Points 兌換監聽組件"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.settings = get_settings()
        self.redemption_repo = RedemptionConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]

    def _generate_oauth_url(self) -> str:
        """返回前端頁面 URL"""
        return self.settings.frontend_url

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """Channel Points 兌換事件"""
        LOGGER.debug(f"[DEBUG] event_custom_redemption_add 觸發！Payload 類型: {type(payload)}")

        user_name = payload.user.display_name or payload.user.name
        reward_title = payload.reward.title
        reward_cost = payload.reward.cost
        user_input = payload.user_input or ""

        LOGGER.info(
            f"[Channel Points] {user_name} 兌換「{reward_title}」"
            f"(花費 {reward_cost} 點數，頻道: {payload.broadcaster.name})"
        )
        if user_input:
            LOGGER.debug(f"[Channel Points] 用戶輸入: {user_input}")

        await self._handle_redemption(payload)

    async def _handle_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
    ) -> None:
        """處理兌換事件（DB 驅動比對）"""
        reward_title = payload.reward.title
        user_name = payload.user.display_name or payload.user.name
        channel_id = payload.broadcaster.id

        # Look up matching redemption config from DB
        config = await self.redemption_repo.find_by_reward_name(channel_id, reward_title)
        if not config:
            LOGGER.debug(f"[Channel Points] No matching redemption config for: {reward_title}")
            return

        if config.action_type == "niibot_auth" and user_name:
            owner_id = self.settings.owner_id
            if channel_id == owner_id:
                await self._handle_niibot_redemption(payload, user_name)
            else:
                LOGGER.warning(
                    f"[Niibot] {user_name} 嘗試在非 owner 頻道 ({payload.broadcaster.name}) 兌換 Niibot"
                )
        elif config.action_type == "first" and user_name:
            await self._handle_first_redemption(payload, user_name)
        elif config.action_type == "vip":
            LOGGER.info(f"[Action] {user_name} 兌換了 VIP 獎勵")
            await self._handle_vip_redemption(payload, user_name)

    async def _handle_vip_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str | None,
    ) -> None:
        """處理 VIP 獎勵兌換"""
        try:
            broadcaster = payload.broadcaster
            await broadcaster.add_vip(user=payload.user)

            success_message = f"恭喜 {user_name}，成為尊榮的 VIP 大人！"
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

            if "422" in error_str:
                if "moderator" in error_str.lower():
                    LOGGER.warning(
                        f"[VIP] {user_name} 已經是 Moderator，無法授予 VIP（Twitch 限制）"
                    )
                    error_message = f"{user_name}，你已經是 Moderator 了！"
                elif "already a vip" in error_str.lower():
                    LOGGER.info(f"[VIP] {user_name} 已經是 VIP")
                    error_message = f"{user_name}，你已經是 VIP 了！"
                else:
                    LOGGER.error(f"[VIP] 授予 VIP 身分失敗 (422): {e}")
                    error_message = f"{user_name}，VIP 授予失敗，請聯繫管理員！"
            else:
                # 其他錯誤
                LOGGER.error(f"[VIP] 授予 VIP 身分失敗: {e}")
                error_message = f"{user_name}，VIP 授予失敗，請聯繫管理員！"

            # 發送錯誤訊息
            try:
                await payload.broadcaster.send_message(
                    message=error_message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )
            except Exception:
                pass  # 如果連錯誤訊息都發送失敗，就只記錄在 log

    async def _handle_first_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理搶第一遊戲兌換"""
        try:
            broadcaster = payload.broadcaster
            announcement_message = f"恭喜 {user_name}，搶到沙發！"

            try:
                await broadcaster.send_announcement(
                    message=announcement_message,
                    moderator=self.bot.bot_id,
                    color="primary",
                )
                LOGGER.info(f"[First] {user_name} 搶到第一，已發送公告")
            except Exception as e:
                LOGGER.warning(f"[First] 發送公告失敗: {e}，fallback 到普通訊息")
                fallback_message = f"恭喜 {user_name}，搶到第一！"
                try:
                    await broadcaster.send_message(
                        message=fallback_message,
                        sender=self.bot.bot_id,
                        token_for=self.bot.bot_id,
                    )
                    LOGGER.info(f"[First] 已發送普通訊息給 {user_name}")
                except Exception as fallback_error:
                    LOGGER.error(f"[First] 連 fallback 都失敗: {fallback_error}")

        except Exception as e:
            LOGGER.error(f"[First] 處理搶第一兌換時發生錯誤: {e}")

    async def _handle_niibot_redemption(
        self,
        payload: twitchio.ChannelPointsRedemptionAdd,
        user_name: str,
    ) -> None:
        """處理 Niibot 獎勵兌換"""
        try:
            try:
                oauth_url = self._generate_oauth_url()
            except ValueError as e:
                LOGGER.error(f"[Niibot] 生成 OAuth URL 失敗: {e}")
                return

            broadcaster = payload.broadcaster
            public_message = f"{user_name}，已將授權連結發送至你的 Twitch 私訊！"
            try:
                await broadcaster.send_message(
                    message=public_message,
                    sender=self.bot.bot_id,
                    token_for=self.bot.bot_id,
                )
                LOGGER.info(f"[Niibot] 已發送確認訊息給 {user_name}")
            except Exception as e:
                LOGGER.warning(f"[Niibot] 發送公開訊息失敗: {e}")

            whisper_message = f"請點擊以下連結，授權 Niibot 存取你的頻道：{oauth_url}"
            try:
                bot_user = self.bot.create_partialuser(user_id=self.bot.bot_id)
                await bot_user.send_whisper(
                    to_user=payload.user,  # 接收者
                    message=whisper_message,
                )
                LOGGER.info(f"[Niibot] 已發送私訊給 {user_name}")
            except Exception as e:
                LOGGER.error(f"[Niibot] 發送私訊失敗: {e}")
                fallback_message = f"{user_name}，私訊發送失敗，請聯繫 Bot Owner 獲取授權連結！"
                try:
                    await broadcaster.send_message(
                        message=fallback_message,
                        sender=self.bot.bot_id,
                        token_for=self.bot.bot_id,
                    )
                    LOGGER.info("[Niibot] 已 fallback 到聊天室")
                except Exception as fallback_error:
                    LOGGER.error(f"[Niibot] Fallback 也失敗: {fallback_error}")

        except Exception as e:
            LOGGER.error(f"[Niibot] 處理兌換時發生錯誤: {e}")


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(ChannelPointsComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
