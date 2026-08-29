"""Single source of truth for configurable Twitch notification events.

Each channel is a tenant and may customise the chat message the bot posts when
one of these events fires. Defining "an event" used to mean editing several
unsynced places; adding ``resub`` / ``gift_sub`` missed the EventSub
subscription list, so they silently never fired. Each catalog entry binds, per
event type: the ``event_configs`` DB key (+ migration 053 CHECK), the DB seed
(template / enabled / options), the ``$(name)`` template variables, and the
twitchio EventSub class that delivers it (or ``None``).

``backend/shared/`` is imported by the api and discord services too, so this
module must NOT import ``twitchio``. ``twitch/core/subscriptions.py`` maps
``subscription_class`` (a bare string) to a real ``eventsub`` factory;
``tests/twitch/test_event_catalog.py`` keeps the layers consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, get_args

EventKey = Literal["follow", "subscribe", "resub", "gift_sub", "raid", "bits"]

# Twitch sub-tier code -> display label. Used both when rendering the $(tier)
# event variable (twitch service) and when backfilling viewer_channel_status
# from the Helix subscriptions endpoint (analytics repo).
TIER_LABELS = {"1000": "T1", "2000": "T2", "3000": "T3"}


def tier_label(tier: str) -> str:
    """``"1000"`` -> ``"T1"``; unknown codes pass through unchanged."""
    return TIER_LABELS.get(tier, tier)


@dataclass(frozen=True)
class EventVariable:
    """A ``$(name)`` placeholder a template for this event may reference."""

    name: str
    description: str  # shown in the dashboard's variable picker


@dataclass(frozen=True)
class EventDef:
    key: EventKey
    default_template: str
    default_enabled: bool
    variables: tuple[EventVariable, ...]
    # twitchio ``eventsub`` class name, resolved to a factory in the twitch
    # service. ``None`` = a listener exists but no live subscription yet.
    subscription_class: str | None
    default_options: dict = field(default_factory=dict)


EVENT_CATALOG: tuple[EventDef, ...] = (
    EventDef(
        key="follow",
        default_template="感謝 $(user) 的追隨！",
        default_enabled=False,
        variables=(EventVariable("user", "追隨者名稱"),),
        subscription_class="ChannelFollowSubscription",
    ),
    EventDef(
        key="subscribe",
        default_template="感謝 $(user) 的訂閱！",
        default_enabled=False,
        variables=(
            EventVariable("user", "訂閱者名稱"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)"),
        ),
        subscription_class="ChannelSubscribeSubscription",
    ),
    EventDef(
        key="resub",
        default_template="感謝 $(user) 連續訂閱 $(months) 個月！",
        default_enabled=False,
        variables=(
            EventVariable("user", "訂閱者名稱"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)"),
            EventVariable("months", "本次訂閱月數"),
            EventVariable("streak", "連續訂閱月數"),
            EventVariable("message", "訂閱留言內容"),
        ),
        subscription_class="ChannelSubscribeMessageSubscription",
    ),
    EventDef(
        key="gift_sub",
        default_template="感謝 $(user) 贈送了 $(total) 個訂閱！",
        default_enabled=False,
        variables=(
            EventVariable("user", "贈禮者名稱"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)"),
            EventVariable("total", "本次贈禮數量"),
            EventVariable("cumulative", "累計贈禮總數"),
        ),
        subscription_class="ChannelSubscriptionGiftSubscription",
    ),
    EventDef(
        key="raid",
        default_template="$(user) 帶了 $(count) 個新朋友降落！",
        default_enabled=True,
        variables=(
            EventVariable("user", "揪團者名稱"),
            EventVariable("count", "觀眾數量"),
        ),
        subscription_class="ChannelRaidSubscription",
        default_options={"auto_shoutout": True},
    ),
    EventDef(
        key="bits",
        default_template="感謝 $(user) 投出了 $(amount) 小奇點！",
        default_enabled=False,
        variables=(
            EventVariable("user", "Cheer 者名稱"),
            EventVariable("amount", "小奇點數量"),
            EventVariable("message", "Cheer 留言"),
        ),
        subscription_class="ChannelCheerSubscription",
        default_options={"tiers": []},
    ),
)

EVENT_KEYS: tuple[EventKey, ...] = tuple(e.key for e in EVENT_CATALOG)

# The Literal and the data must not drift apart.
assert set(EVENT_KEYS) == set(get_args(EventKey)), "EventKey literal out of sync with EVENT_CATALOG"
