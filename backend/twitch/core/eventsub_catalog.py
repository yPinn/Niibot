"""EventSub subscription definitions — the full set created for every channel.

This is the *catalog / factory* layer (pure functions, no state); runtime
subscribe/unsubscribe state lives in ``core.subscription_manager``.

The template-driven notification events (follow / subscribe / raid / bits) are
derived from ``shared.events.EVENT_CATALOG`` so the catalog stays the single
source of truth. ``tests/twitch/test_event_catalog.py`` asserts that every
catalog entry carrying a ``subscription_class`` has a factory here. The rest
are fixed infrastructure subscriptions with no per-channel config.
"""

from collections.abc import Callable

from twitchio import eventsub

from shared.events import EVENT_CATALOG
from shared.twitch_scopes import (
    BOT_SCOPES,
    BROADCASTER_SCOPES,
    TWITCH_CAPABILITIES,
    capability_available,
)

# catalog.subscription_class -> (broadcaster_id, bot_id) -> SubscriptionPayload
_CATALOG_FACTORIES: dict[str, Callable[[str, str], eventsub.SubscriptionPayload]] = {
    # moderator_user_id = bot: the bot reads followers as a moderator, so
    # `moderator:read:followers` lives on the bot token, not the broadcaster.
    # Requires the bot to already be a mod — re-subscribed via
    # `SubscriptionManager.resubscribe_follow` once mod is granted.
    "ChannelFollowSubscription": lambda bc, bot: eventsub.ChannelFollowSubscription(
        broadcaster_user_id=bc, moderator_user_id=bot
    ),
    "ChannelSubscribeSubscription": lambda bc, _bot: eventsub.ChannelSubscribeSubscription(
        broadcaster_user_id=bc
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
    broadcaster_user_id: str,
    bot_id: str,
    *,
    broadcaster_scopes: set[str],
    bot_scopes: set[str],
    enabled_capabilities: set[str],
) -> list[eventsub.SubscriptionPayload]:
    """Infrastructure subscriptions — not template-driven, no per-channel config."""
    subscriptions: list[eventsub.SubscriptionPayload] = [
        eventsub.StreamOnlineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionBeginSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionUpdateSubscription(broadcaster_user_id=broadcaster_user_id),
        eventsub.SharedChatSessionEndSubscription(broadcaster_user_id=broadcaster_user_id),
    ]
    if capability_available("bot_chat", bot_scopes) and capability_available(
        "broadcaster_chat", broadcaster_scopes
    ):
        subscriptions.extend(
            [
                eventsub.ChatMessageSubscription(
                    broadcaster_user_id=broadcaster_user_id, user_id=bot_id
                ),
                # Delivers sub / resub / sub_gift greetings. Dedicated
                # subscription topics below remain analytics-only.
                eventsub.ChatNotificationSubscription(
                    broadcaster_user_id=broadcaster_user_id, user_id=bot_id
                ),
            ]
        )
    if capability_available("channel_points", broadcaster_scopes):
        subscriptions.append(
            eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=broadcaster_user_id)
        )
    if capability_available("subscriptions", broadcaster_scopes):
        subscriptions.append(
            eventsub.ChannelSubscriptionEndSubscription(broadcaster_user_id=broadcaster_user_id)
        )
    if capability_available("vip_management", broadcaster_scopes):
        subscriptions.extend(
            [
                eventsub.ChannelVIPAddSubscription(broadcaster_user_id=broadcaster_user_id),
                eventsub.ChannelVIPRemoveSubscription(broadcaster_user_id=broadcaster_user_id),
            ]
        )
    if "moderator_sync_realtime" in enabled_capabilities and capability_available(
        "moderator_sync_realtime", broadcaster_scopes
    ):
        subscriptions.extend(
            [
                eventsub.ChannelModeratorAddSubscription(broadcaster_user_id=broadcaster_user_id),
                eventsub.ChannelModeratorRemoveSubscription(
                    broadcaster_user_id=broadcaster_user_id
                ),
            ]
        )
    return subscriptions


def get_channel_subscriptions(
    broadcaster_user_id: str,
    bot_id: str,
    *,
    broadcaster_scopes: set[str] | None = None,
    bot_scopes: set[str] | None = None,
    enabled_capabilities: set[str] | None = None,
) -> list[eventsub.SubscriptionPayload]:
    """Generate the authorized EventSub plan for one channel.

    ``None`` preserves the complete current OAuth grant for pure callers and
    tests. Runtime callers pass the scopes stored with each credential.
    """
    broadcaster_grants = set(
        BROADCASTER_SCOPES if broadcaster_scopes is None else broadcaster_scopes
    )
    bot_grants = set(BOT_SCOPES if bot_scopes is None else bot_scopes)
    active_capabilities = set(enabled_capabilities or ())
    subs = _fixed_subscriptions(
        broadcaster_user_id,
        bot_id,
        broadcaster_scopes=broadcaster_grants,
        bot_scopes=bot_grants,
        enabled_capabilities=active_capabilities,
    )
    for event in EVENT_CATALOG:
        factory = _CATALOG_FACTORIES.get(event.subscription_class or "")
        if factory is None:
            continue
        if event.capability_key:
            definition = TWITCH_CAPABILITIES[event.capability_key]
            grants = bot_grants if definition.credential == "bot" else broadcaster_grants
            if not capability_available(event.capability_key, grants):
                continue
        subs.append(factory(broadcaster_user_id, bot_id))
    return subs
