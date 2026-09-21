"""Consistency tests for the event catalog (shared.events.EVENT_CATALOG).

The point of the catalog is that adding an event type in one layer but not the
others fails loudly here instead of silently never firing (which is exactly how
resub / gift_sub shipped broken). Each catalog entry is checked against:

- the twitchio EventSub factory map in twitch.core.eventsub_catalog
- the twitchio listener method on EventsComponent
- the event_configs CHECK constraint (latest event-type migration)
- the DEFAULT_TEMPLATES / DEFAULT_ENABLED seed dicts

Plus: shared.events must not drag twitchio into the api / discord services, and
get_channel_subscriptions must still produce exactly today's subscription set.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.events import EventsComponent
from twitch.core.eventsub_catalog import _CATALOG_FACTORIES, get_channel_subscriptions
from twitchio import eventsub

from shared.events import EVENT_CATALOG, EVENT_KEYS
from shared.repositories.event_config import DEFAULT_ENABLED, DEFAULT_TEMPLATES, EVENT_TYPES

_MIGRATIONS = Path(__file__).parents[2] / "shared/migrations/versions"
_MIGRATION_WATCH_STREAK = _MIGRATIONS / "130_add_watch_streak_event.sql"
_MIGRATION_EVENT_TYPES = _MIGRATION_WATCH_STREAK
_MIGRATION_044 = _MIGRATIONS / "044_stream_events_add_cheer_type.sql"


def _check_constraint_values(sql: str) -> set[str]:
    """Pull the ``event_type IN ('a', 'b', ...)`` literal list from a migration."""
    inner = re.search(r"event_type IN \(([^)]+)\)", sql).group(1)
    return set(re.findall(r"'([^']+)'", inner))


@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
class TestCatalogConsistency:
    def test_listener_exists(self, event):
        name = _DRIVERS[event.key][0]
        assert callable(getattr(EventsComponent, name, None)), (
            f"{event.key}: EventsComponent.{name} listener missing"
        )

    def test_subscription_class_has_factory(self, event):
        if event.subscription_class is None:
            pytest.skip(f"{event.key}: delivered by the fixed chat.notification sub")
        assert event.subscription_class in _CATALOG_FACTORIES
        assert hasattr(eventsub, event.subscription_class)

    def test_in_migration_check_constraint(self, event):
        allowed = _check_constraint_values(_MIGRATION_EVENT_TYPES.read_text(encoding="utf-8"))
        assert event.key in allowed

    def test_seed_dicts_cover_key(self, event):
        assert event.key in DEFAULT_TEMPLATES
        assert event.key in DEFAULT_ENABLED
        assert event.key in EVENT_TYPES


def test_no_factory_without_catalog_entry():
    """Every factory must belong to a catalog entry (no orphans)."""
    catalog_classes = {e.subscription_class for e in EVENT_CATALOG}
    assert set(_CATALOG_FACTORIES) <= catalog_classes


def test_seed_dicts_have_no_extra_keys():
    assert set(DEFAULT_TEMPLATES) == set(EVENT_KEYS)
    assert set(DEFAULT_ENABLED) == set(EVENT_KEYS)


def test_shared_events_does_not_import_twitchio():
    """api / discord import shared.* — the catalog must stay twitchio-free.

    Runs in a clean subprocess so an already-imported twitchio (this file pulls
    it in) can't mask a real dependency.
    """
    code = (
        "import sys; import shared.events; "
        "sys.exit(1 if any(m == 'twitchio' or m.startswith('twitchio.') "
        "for m in sys.modules) else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "shared.events imported twitchio (breaks api/discord)"


def _key(sub: eventsub.SubscriptionPayload) -> tuple:
    return (sub.type, sub.version, tuple(sorted(sub.condition.items())))


def test_channel_subscription_set():
    """Snapshot of every EventSub subscription created per channel.

    Update this list deliberately when adding/removing a subscription — the
    friction is the point.
    """
    bc, bot = "bc-1", "bot-1"
    expected = [
        eventsub.ChatMessageSubscription(broadcaster_user_id=bc, user_id=bot),
        eventsub.StreamOnlineSubscription(broadcaster_user_id=bc),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=bc),
        eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=bc),
        eventsub.SharedChatSessionBeginSubscription(broadcaster_user_id=bc),
        eventsub.SharedChatSessionUpdateSubscription(broadcaster_user_id=bc),
        eventsub.SharedChatSessionEndSubscription(broadcaster_user_id=bc),
        eventsub.ChannelSubscriptionEndSubscription(broadcaster_user_id=bc),
        eventsub.ChannelModeratorAddSubscription(broadcaster_user_id=bc),
        eventsub.ChannelModeratorRemoveSubscription(broadcaster_user_id=bc),
        eventsub.ChannelVIPAddSubscription(broadcaster_user_id=bc),
        eventsub.ChannelVIPRemoveSubscription(broadcaster_user_id=bc),
        # catalog-derived (subscription_class set)
        eventsub.ChatNotificationSubscription(broadcaster_user_id=bc, user_id=bot),
        eventsub.ChannelFollowSubscription(broadcaster_user_id=bc, moderator_user_id=bot),
        eventsub.ChannelSubscribeSubscription(broadcaster_user_id=bc),
        eventsub.ChannelSubscriptionGiftSubscription(broadcaster_user_id=bc),
        eventsub.ChannelRaidSubscription(to_broadcaster_user_id=bc),
        eventsub.ChannelCheerSubscription(broadcaster_user_id=bc),
    ]
    got = get_channel_subscriptions(bc, bot)
    assert {_key(s) for s in got} == {_key(s) for s in expected}
    assert len(got) == len(expected)


# ---------------------------------------------------------------------------
# Schema-layer guards — every new facet of EventDef gets a drift check
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\$\((@?\w+)\)")


@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
class TestCatalogSchema:
    def test_default_template_uses_only_declared_variables(self, event):
        used = set(_VAR_RE.findall(event.default_template))
        assert used <= event.variable_names, (
            f"{event.key}: template uses undeclared {used - event.variable_names}"
        )

    def test_variables_are_unique_snake_case_with_samples(self, event):
        names = [v.name for v in event.variables]
        assert len(names) == len(set(names)), f"{event.key}: duplicate variable name"
        for v in event.variables:
            assert re.fullmatch(r"[a-z][a-z_]*", v.name), f"{event.key}: bad var name {v.name!r}"
            assert v.sample, f"{event.key}: variable {v.name} has no preview sample"
            assert v.description, f"{event.key}: variable {v.name} has no description"

    def test_options_schema_matches_default_options(self, event):
        assert event.default_options == {o.key: o.default for o in event.options_schema}
        for opt in event.options_schema:
            assert opt.type == "boolean"
            assert isinstance(opt.default, bool)
            assert opt.label and opt.description

    def test_display_metadata_present(self, event):
        assert event.display_name and event.category_label and event.accent

    def test_count_source_is_a_valid_stream_events_bucket(self, event):
        if event.count_source is None:
            pytest.skip(f"{event.key}: writes no stream_events row")
        allowed = _check_constraint_values(_MIGRATION_044.read_text(encoding="utf-8"))
        assert event.count_source in allowed, (
            f"{event.key}: count_source {event.count_source!r} not in migration 044 CHECK {allowed}"
        )


def test_bits_tiers_option_is_gone():
    """The dead ``{"tiers": []}`` option must not reappear."""
    bits = next(e for e in EVENT_CATALOG if e.key == "bits")
    assert "tiers" not in bits.default_options
    assert bits.options_schema == ()


def test_catalog_is_in_display_order():
    assert list(EVENT_KEYS) == [
        "follow",
        "subscribe",
        "resub",
        "gift_sub",
        "gift_recipient",
        "watch_streak",
        "bits",
        "raid",
    ]


def test_watch_streak_forward_migration_updates_event_check():
    sql = _MIGRATION_WATCH_STREAK.read_text(encoding="utf-8")
    assert _check_constraint_values(sql) == set(EVENT_KEYS)


# ---------------------------------------------------------------------------
# The drift that shipped resub broken: catalog says a variable exists, the
# listener never passes it (or vice versa).
# ---------------------------------------------------------------------------


def _driver_component() -> tuple[EventsComponent, MagicMock]:
    bot = MagicMock()
    bot.bot_id = "bot-1"
    bot._bot_is_mod = {"ch"}
    bot.sessions.session_id = MagicMock(return_value=None)
    bot.event_configs.get_config = AsyncMock(return_value=SimpleNamespace(options={}))
    for m in (
        "upsert_viewer_follow_status",
        "upsert_viewer_subscription",
        "upsert_viewer_sub_prime",
        "upsert_viewer_gift_count",
        "record_follow_event",
        "record_subscribe_event",
        "record_cheer_event",
        "record_raid_event",
    ):
        setattr(bot.analytics, m, AsyncMock())
    comp = EventsComponent(bot)
    comp._notify = AsyncMock(return_value=True)
    return comp, bot


def _fake_dedicated(key: str) -> MagicMock:
    """A fake payload for an event with its own dedicated EventSub type."""
    p = MagicMock()
    p.broadcaster.name, p.broadcaster.id = "bc", "ch"
    if key == "follow":
        p.user.display_name, p.user.name, p.user.id = "Follower", "follower", "u1"
        p.followed_at = datetime.now(UTC)
    elif key == "gift_sub":
        p.anonymous = False
        p.user.display_name, p.user.name, p.user.id = "Gifter", "gifter", "u1"
        p.tier, p.total, p.cumulative_total = "1000", 5, 20
    elif key == "bits":
        p.anonymous = False
        p.user.display_name, p.user.name, p.user.id = "Cheerer", "cheerer", "u1"
        p.bits, p.message = 100, "pog"
    elif key == "raid":
        p.from_broadcaster.display_name, p.from_broadcaster.name = "Raider", "raider"
        p.from_broadcaster.id = "r1"
        p.to_broadcaster.name, p.to_broadcaster.id = "bc", "ch"
        p.to_broadcaster.send_shoutout = AsyncMock()
        p.viewer_count = 42
    return p


def _fake_notification(notice_type: str) -> MagicMock:
    """A fake channel.chat.notification payload used by configurable events."""
    p = MagicMock()
    p.notice_type = notice_type
    p.broadcaster.name, p.broadcaster.id = "bc", "ch"
    p.chatter.display_name, p.chatter.name, p.chatter.id = "Chatter", "chatter", "u1"
    p.anonymous = False
    p.text = "yay"
    p.sub = p.resub = p.sub_gift = p.prime_paid_upgrade = p.watch_streak = None
    if notice_type == "sub":
        p.sub = SimpleNamespace(prime=False, tier="1000", months=1)
    elif notice_type == "resub":
        p.resub = SimpleNamespace(
            prime=False, gift=False, tier="2000", months=1, cumulative_months=10, streak_months=3
        )
    elif notice_type == "sub_gift":
        p.sub_gift = SimpleNamespace(
            tier="1000",
            months=1,
            community_gift_id=None,
            recipient=SimpleNamespace(display_name="Rec", name="rec"),
        )
    elif notice_type == "watch_streak":
        p.watch_streak = SimpleNamespace(streak=7, points=450)
    return p


# catalog key -> (EventsComponent listener method, fake-payload factory)
_DRIVERS = {
    "follow": ("event_follow", lambda: _fake_dedicated("follow")),
    "subscribe": ("event_chat_notification", lambda: _fake_notification("sub")),
    "resub": ("event_chat_notification", lambda: _fake_notification("resub")),
    "gift_sub": ("event_subscription_gift", lambda: _fake_dedicated("gift_sub")),
    "gift_recipient": ("event_chat_notification", lambda: _fake_notification("sub_gift")),
    "watch_streak": ("event_chat_notification", lambda: _fake_notification("watch_streak")),
    "bits": ("event_cheer", lambda: _fake_dedicated("bits")),
    "raid": ("event_raid", lambda: _fake_dedicated("raid")),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
async def test_notify_variables_match_catalog(event):
    comp, _bot = _driver_component()
    listener_name, make_payload = _DRIVERS[event.key]

    await getattr(comp, listener_name)(make_payload())

    comp._notify.assert_awaited_once()
    args = comp._notify.await_args.args
    assert args[1] == event.key
    assert set(args[2]) == event.variable_names, (
        f"{event.key}: listener passed {set(args[2])}, catalog declares {event.variable_names}"
    )


@pytest.mark.asyncio
async def test_channel_subscribe_is_analytics_only():
    """The greeting moved to event_chat_notification; channel.subscribe now only
    keeps analytics current (for real subs and gift recipients alike)."""
    comp, bot = _driver_component()
    payload = MagicMock()
    payload.broadcaster.name, payload.broadcaster.id = "bc", "ch"
    payload.user.display_name, payload.user.name, payload.user.id = "Sub", "sub", "u1"
    payload.tier, payload.gift = "1000", False

    await comp.event_subscription(payload)

    comp._notify.assert_not_awaited()
    bot.analytics.upsert_viewer_subscription.assert_awaited_once()


@pytest.mark.asyncio
async def test_gift_bomb_recipient_skipped_by_default():
    comp, _bot = _driver_component()
    payload = _fake_notification("sub_gift")
    payload.sub_gift.community_gift_id = "bomb-1"  # part of a community gift

    await comp.event_chat_notification(payload)

    comp._notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_watch_streak_notification_maps_shared_milestone():
    comp, _bot = _driver_component()

    await comp.event_chat_notification(_fake_notification("watch_streak"))

    comp._notify.assert_awaited_once_with(
        "ch",
        "watch_streak",
        {"user": "Chatter", "@user": "@Chatter", "streak": "7", "points": "450"},
        label="[bc] WatchStreak: Chatter x7 (+450)",
    )


@pytest.mark.asyncio
async def test_watch_streak_without_payload_is_ignored():
    comp, _bot = _driver_component()
    payload = _fake_notification("unknown")
    payload.notice_type = "watch_streak"

    await comp.event_chat_notification(payload)

    comp._notify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Prime flag capture — the only source is channel.chat.notification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sub_notice_records_prime_flag():
    comp, bot = _driver_component()
    payload = _fake_notification("sub")
    payload.sub.prime = True

    await comp.event_chat_notification(payload)

    bot.analytics.upsert_viewer_sub_prime.assert_awaited_once()
    assert bot.analytics.upsert_viewer_sub_prime.await_args.kwargs["is_prime"] is True


@pytest.mark.asyncio
async def test_gifted_resub_does_not_record_prime():
    comp, bot = _driver_component()
    payload = _fake_notification("resub")
    payload.resub.gift = True  # announcing a gifted sub — not the person's own payment

    await comp.event_chat_notification(payload)

    bot.analytics.upsert_viewer_sub_prime.assert_not_awaited()


@pytest.mark.asyncio
async def test_prime_paid_upgrade_records_paid():
    comp, bot = _driver_component()
    payload = _fake_notification("prime_paid_upgrade")
    payload.prime_paid_upgrade = SimpleNamespace(tier="1000")

    await comp.event_chat_notification(payload)

    bot.analytics.upsert_viewer_sub_prime.assert_awaited_once()
    assert bot.analytics.upsert_viewer_sub_prime.await_args.kwargs["is_prime"] is False


@pytest.mark.asyncio
async def test_anonymous_chatter_prime_not_recorded():
    comp, bot = _driver_component()
    payload = _fake_notification("sub")
    payload.anonymous = True

    await comp.event_chat_notification(payload)

    bot.analytics.upsert_viewer_sub_prime.assert_not_awaited()
