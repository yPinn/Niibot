import logging
import twitchio
from twitchio.ext import commands
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Bot
else:
    from twitchio.ext.commands import Bot


LOGGER: logging.Logger = logging.getLogger("EventComponent")


class EventComponent(commands.Component):
    """EventSub event listener component.

    Features:
    - Listen to follow events and send thank you messages
    - Listen to subscription events and send thank you messages
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==================== Follow Events ====================

    @commands.Component.listener()
    async def event_channel_follow(
        self,
        payload: twitchio.ChannelFollowData,
    ) -> None:
        """Triggered when someone follows the channel.

        Args:
            payload: Follow data containing:
                - user: Follower info (user.name, user.display_name)
                - broadcaster: Channel info
                - followed_at: Follow time
        """
        user_name = payload.user.display_name or payload.user.name
        broadcaster_name = payload.broadcaster.name

        LOGGER.info(f"[Follow] {user_name} followed {broadcaster_name}")

        # Send thank you message
        try:
            message = f"感謝 {user_name} 的追隨"
            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[Follow] Sent thank you message to {user_name}")
        except Exception as e:
            LOGGER.error(f"[Follow] Failed to send message: {e}")

    # ==================== Subscription Events ====================

    @commands.Component.listener()
    async def event_subscription(
        self,
        payload: twitchio.SubscriptionData,
    ) -> None:
        """Triggered when someone receives a subscription (self-sub or gifted).

        Args:
            payload: Subscription data containing:
                - user: Subscriber info
                - broadcaster: Channel info
                - tier: Subscription tier (1000, 2000, 3000)
                - is_gift: Whether it's a gift sub
        """
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

        # Send thank you message (unified for both self-sub and gift)
        try:
            message = f"感謝 {user_name} 的訂閱"

            await payload.broadcaster.send_message(
                message=message,
                sender=self.bot.bot_id,
                token_for=self.bot.bot_id,
            )
            LOGGER.info(f"[Sub] Sent thank you message to {user_name}")
        except Exception as e:
            LOGGER.error(f"[Sub] Failed to send message: {e}")


async def setup(bot: commands.Bot) -> None:
    """Entry point for the module."""
    await bot.add_component(EventComponent(bot))


async def teardown(bot: commands.Bot) -> None:
    """Optional teardown coroutine for cleanup."""
    ...
