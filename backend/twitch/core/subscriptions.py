from typing import TYPE_CHECKING

from twitchio import eventsub

if TYPE_CHECKING:
    pass


def get_channel_subscriptions(
    broadcaster_user_id: str, bot_id: str
) -> list[eventsub.SubscriptionPayload]:
    """Generate standard EventSub subscriptions for a channel."""
    return [
        eventsub.ChatMessageSubscription(broadcaster_user_id=broadcaster_user_id, user_id=bot_id),
        eventsub.StreamOnlineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelFollowSubscription(
            broadcaster_user_id=broadcaster_user_id, moderator_user_id=bot_id
        ),
        eventsub.ChannelSubscribeSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelRaidSubscription(to_broadcaster_user_id=broadcaster_user_id),
    ]
