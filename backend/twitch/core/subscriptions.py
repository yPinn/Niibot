"""EventSub subscriptions created for every monitored channel.

The template-driven notification events (follow / subscribe / raid / bits) are
derived from ``shared.events.EVENT_CATALOG`` so the catalog stays the single
source of truth. ``tests/twitch/test_event_catalog.py`` asserts that every
catalog entry carrying a ``subscription_class`` has a factory here. The rest
are fixed infrastructure subscriptions with no per-channel config.
"""

from collections.abc import Callable

from twitchio import eventsub

from shared.events import EVENT_CATALOG

# catalog.subscription_class -> (broadcaster_id, bot_id) -> SubscriptionPayload
_CATALOG_FACTORIES: dict[str, Callable[[str, str], eventsub.SubscriptionPayload]] = {
    # moderator_user_id = bot: the bot reads followers as a moderator, so
    # `moderator:read:followers` lives on the bot token, not the broadcaster.
    # Requires the bot to already be a mod — re-subscribed via
    # `resubscribe_follow` once mod is granted (see _channel_mixin).
    "ChannelFollowSubscription": lambda bc, bot: eventsub.ChannelFollowSubscription(
        broadcaster_user_id=bc, moderator_user_id=bot
    ),
    "ChannelSubscribeSubscription": lambda bc, _bot: eventsub.ChannelSubscribeSubscription(
        broadcaster_user_id=bc
    ),
    "ChannelSubscribeMessageSubscription": lambda bc, _bot: (
        eventsub.ChannelSubscribeMessageSubscription(broadcaster_user_id=bc)
    ),
    "ChannelSubscriptionGiftSubscription": lambda bc, _bot: (
        eventsub.ChannelSubscriptionGiftSubscription(broadcaster_user_id=bc)
    ),
    "ChannelCheerSubscription": lambda bc, _bot: eventsub.ChannelCheerSubscription(
        broadcaster_user_id=bc
    ),
    "ChannelRaidSubscription": lambda bc, _bot: eventsub.ChannelRaidSubscription(
        to_broadcaster_user_id=bc
    ),
}


def _fixed_subscriptions(
    broadcaster_user_id: str, bot_id: str
) -> list[eventsub.SubscriptionPayload]:
    """Infrastructure subscriptions — not template-driven, no per-channel config."""
    return [
        eventsub.ChatMessageSubscription(broadcaster_user_id=broadcaster_user_id, user_id=bot_id),
        eventsub.StreamOnlineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionBeginSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionUpdateSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionEndSubscription(broadcaster_user_id=broadcaster_user_id),
        # analytics-only (viewer status upserts) — no template / dashboard toggle
        eventsub.ChannelSubscriptionEndSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelModeratorAddSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelModeratorRemoveSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelVIPAddSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.ChannelVIPRemoveSubscription(broadcaster_user_id=broadcaster_user_id),
    ]


def get_channel_subscriptions(
    broadcaster_user_id: str, bot_id: str
) -> list[eventsub.SubscriptionPayload]:
    """Generate the full EventSub subscription set for one channel."""
    subs = _fixed_subscriptions(broadcaster_user_id, bot_id)
    for event in EVENT_CATALOG:
        factory = _CATALOG_FACTORIES.get(event.subscription_class or "")
        if factory is not None:
            subs.append(factory(broadcaster_user_id, bot_id))
    return subs
