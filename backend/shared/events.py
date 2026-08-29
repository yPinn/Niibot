"""Single source of truth for configurable Twitch notification events.

Each channel is a tenant and may customise the chat message the bot posts when
one of these events fires. Defining "an event" used to mean editing several
unsynced places; adding ``resub`` / ``gift_sub`` missed the EventSub
subscription list, so they silently never fired. Each catalog entry binds, per
event type: the ``event_configs`` DB key (+ migration 053 CHECK), the DB seed
(template / enabled / options), the ``$(name)`` template variables, the display
metadata the dashboard renders, the per-event options schema, the
``stream_events`` bucket its trigger count reads from, and the twitchio EventSub
class that delivers it.

``backend/shared/`` is imported by the api and discord services too, so this
module must NOT import ``twitchio``. ``twitch/core/eventsub_catalog.py`` maps
``subscription_class`` (a bare string) to a real ``eventsub`` factory;
``tests/twitch/test_event_catalog.py`` keeps the layers consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

EventKey = Literal["follow", "subscribe", "resub", "gift_sub", "raid", "bits"]

# Semantic status-token names the dashboard maps to Tailwind classes. Kept as
# bare strings here so shared/ stays framework-free.
AccentToken = Literal[
    "info", "special", "offline", "loading", "follow", "success", "warning", "online"
]

# ``stream_events.event_type`` buckets a trigger count may read from. Constrained
# by the CHECK in migration 044; ``test_event_catalog.py`` cross-checks this.
CountSource = Literal["follow", "subscribe", "cheer", "raid"]

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
    sample: str  # stand-in value the dashboard uses to render a live preview


@dataclass(frozen=True)
class EventOption:
    """One configurable knob for an event, rendered as a form field."""

    key: str
    type: Literal["boolean"]
    label: str
    description: str
    default: bool


@dataclass(frozen=True)
class EventDef:
    key: EventKey
    default_template: str
    default_enabled: bool
    variables: tuple[EventVariable, ...]
    # twitchio ``eventsub`` class name, resolved to a factory in the twitch
    # service. ``None`` = a listener exists but no live subscription yet.
    subscription_class: str | None
    display_name: str  # dashboard row title, e.g. "首次訂閱"
    category_label: str  # dashboard type badge, e.g. "訂閱"
    accent: AccentToken  # type badge colour
    requires_affiliate: bool = False
    # ``stream_events`` bucket the dashboard's trigger count reads. ``None`` when
    # the event writes no stream_events row (count shown as "—", not a fake 0).
    count_source: CountSource | None = None
    options_schema: tuple[EventOption, ...] = ()

    @property
    def default_options(self) -> dict[str, bool]:
        """DB seed for this event's ``options`` column — derived from the schema
        so the two can't drift."""
        return {opt.key: opt.default for opt in self.options_schema}


EVENT_CATALOG: tuple[EventDef, ...] = (
    EventDef(
        key="follow",
        default_template="感謝 $(user) 的追隨！",
        default_enabled=False,
        variables=(EventVariable("user", "追隨者名稱", "小明"),),
        subscription_class="ChannelFollowSubscription",
        display_name="追隨",
        category_label="追隨",
        accent="info",
        count_source="follow",
    ),
    EventDef(
        key="subscribe",
        default_template="感謝 $(user) 的訂閱！",
        default_enabled=False,
        variables=(
            EventVariable("user", "訂閱者名稱", "小明"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)", "T1"),
        ),
        subscription_class="ChannelSubscribeSubscription",
        display_name="首次訂閱",
        category_label="訂閱",
        accent="special",
        requires_affiliate=True,
        count_source="subscribe",
    ),
    EventDef(
        key="resub",
        default_template="感謝 $(user) 訂閱滿 $(total_months) 個月！",
        default_enabled=False,
        variables=(
            EventVariable("user", "訂閱者名稱", "小明"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)", "T2"),
            EventVariable("months", "本次訂閱期長（月）", "1"),
            EventVariable("streak", "連續訂閱月數", "6"),
            EventVariable("total_months", "累計訂閱總月數", "14"),
            EventVariable("message", "訂閱留言內容", "這台真的讚"),
        ),
        subscription_class="ChannelSubscribeMessageSubscription",
        display_name="重新訂閱",
        category_label="訂閱",
        accent="special",
        requires_affiliate=True,
    ),
    EventDef(
        key="gift_sub",
        default_template="感謝 $(user) 贈送了 $(total) 個訂閱！",
        default_enabled=False,
        variables=(
            EventVariable("user", "贈禮者名稱", "大方哥"),
            EventVariable("tier", "訂閱等級 (T1/T2/T3)", "T1"),
            EventVariable("total", "本次贈禮數量", "5"),
            EventVariable("cumulative", "累計贈禮總數", "20"),
        ),
        subscription_class="ChannelSubscriptionGiftSubscription",
        display_name="贈禮訂閱",
        category_label="訂閱",
        accent="special",
        requires_affiliate=True,
    ),
    EventDef(
        key="bits",
        default_template="感謝 $(user) 投出了 $(amount) 小奇點！",
        default_enabled=False,
        variables=(
            EventVariable("user", "Cheer 者名稱", "小明"),
            EventVariable("amount", "小奇點數量", "500"),
            EventVariable("message", "Cheer 留言", "加油"),
        ),
        subscription_class="ChannelCheerSubscription",
        display_name="Cheer",
        category_label="Cheer",
        accent="loading",
        requires_affiliate=True,
        count_source="cheer",
    ),
    EventDef(
        key="raid",
        default_template="$(user) 帶了 $(count) 個新朋友降落！",
        default_enabled=True,
        variables=(
            EventVariable("user", "揪團者名稱", "隔壁棚"),
            EventVariable("count", "觀眾數量", "42"),
            EventVariable("url", "揪團者頻道連結", "https://twitch.tv/somestreamer"),
        ),
        subscription_class="ChannelRaidSubscription",
        display_name="揪團",
        category_label="揪團",
        accent="offline",
        count_source="raid",
        options_schema=(
            EventOption(
                key="auto_shoutout",
                type="boolean",
                label="自動推薦",
                description="揪團時自動執行 /shoutout 展示對方頻道（需要管理員）",
                default=True,
            ),
        ),
    ),
)

EVENT_KEYS: tuple[EventKey, ...] = tuple(e.key for e in EVENT_CATALOG)

# The Literal and the data must not drift apart.
assert set(EVENT_KEYS) == set(get_args(EventKey)), "EventKey literal out of sync with EVENT_CATALOG"
