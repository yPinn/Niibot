"""Single source of truth for configurable Twitch notification events.

Each Twitch channel is a tenant and may customise the chat message the bot
posts when one of these events fires. Historically the definition of "an event"
was smeared across five places that nothing kept in sync — the EventSub
subscription list, the twitchio listener names, the ``event_configs`` DB keys
(+ migration CHECK), the default templates, and the frontend variable labels.
Adding ``resub`` / ``gift_sub`` touched four of them and missed the
subscription list, so those events silently never fired.

This catalog binds everything one event type needs:

- ``key``                — ``event_configs.event_type`` value, API path segment
- ``default_template`` / ``default_enabled`` / ``default_options`` — DB seed
- ``variables``          — ``$(name)`` placeholders a template may use (+ label)
- ``subscription_class`` — twitchio EventSub class that delivers it, or ``None``

``backend/shared/`` is imported by the api and discord services too, so this
module must NOT import ``twitchio``. The twitch service maps
``subscription_class`` (a bare string) to a real ``eventsub`` factory in
``twitch/core/subscriptions.py``; ``tests/twitch/test_event_catalog.py`` keeps
the layers consistent so a missing subscription can't merge again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, get_args

EventKey = Literal["follow", "subscribe", "resub", "gift_sub", "raid", "bits"]


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

_BY_KEY: dict[str, EventDef] = {e.key: e for e in EVENT_CATALOG}


def get_event(key: str) -> EventDef | None:
    return _BY_KEY.get(key)
