import logging
import twitchio
from twitchio.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass
else:
    pass


LOGGER: logging.Logger = logging.getLogger("EventComponent")


class EventComponent(commands.Component):
    """EventSub 事件監聽組件"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Component.listener()
    async def event_follow(
        self,
        payload: twitchio.ChannelFollow,
    ) -> None:
        """追隨事件"""
        LOGGER.debug(f"[Follow] Event triggered! Payload type: {type(payload)}")
        LOGGER.debug(f"[Follow] Payload data: user={payload.user}, broadcaster={payload.broadcaster}")

        user_name = payload.user.display_name or payload.user.name
        broadcaster_name = payload.broadcaster.name

        LOGGER.info(f"[Follow] {user_name} followed {broadcaster_name}")

        try:
            message = f"感謝 {user_name} 的追隨！"
            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[Follow] Sent thank you message to {user_name}")
        except Exception as e:
            LOGGER.error(f"[Follow] Failed to send message: {e}")

    @commands.Component.listener()
    async def event_subscribe(
        self,
        payload: twitchio.ChannelSubscribe,
    ) -> None:
        """訂閱事件"""
        LOGGER.debug(f"[Sub] Event triggered! Payload type: {type(payload)}")
        LOGGER.debug(f"[Sub] Payload data: user={payload.user}, broadcaster={payload.broadcaster}, is_gift={payload.is_gift}")

        user_name = payload.user.display_name or payload.user.name
        broadcaster_name = payload.broadcaster.name
        tier_name = {
            "1000": "T1",
            "2000": "T2",
            "3000": "T3",
        }.get(payload.tier, payload.tier)

        if payload.is_gift:
            LOGGER.info(f"[Sub] {user_name} received {tier_name} gift sub in {broadcaster_name}")
        else:
            LOGGER.info(f"[Sub] {user_name} subscribed {tier_name} in {broadcaster_name}")

        try:
            message = f"感謝 {user_name} 的訂閱！"

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[Sub] Sent thank you message to {user_name}")
        except Exception as e:
            LOGGER.error(f"[Sub] Failed to send message: {e}")


async def setup(bot: commands.Bot) -> None:
    component = EventComponent(bot)
    await bot.add_component(component)
    LOGGER.info("EventComponent loaded with listeners: event_follow, event_subscribe")


async def teardown(bot: commands.Bot) -> None:
    ...
