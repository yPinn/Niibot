"""Consistency tests for the event catalog (shared.events.EVENT_CATALOG).

The point of the catalog is that adding an event type in one layer but not the
others fails loudly here instead of silently never firing (which is exactly how
resub / gift_sub shipped broken). Each catalog entry is checked against:

- the twitchio EventSub factory map in twitch.core.eventsub_catalog
- the twitchio listener method on EventsComponent
- the event_configs CHECK constraint (migration 053)
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

# catalog key -> twitchio dispatch name (the @Component.listener() method)
_LISTENER_BY_KEY = {
    "follow": "event_follow",
    "subscribe": "event_subscription",
    "resub": "event_subscription_message",
    "gift_sub": "event_subscription_gift",
    "raid": "event_raid",
    "bits": "event_cheer",
}

_MIGRATION_053 = (
    Path(__file__).parents[2] / "shared/migrations/versions/053_add_resub_gift_sub_event_types.sql"
)
_MIGRATION_044 = (
    Path(__file__).parents[2] / "shared/migrations/versions/044_stream_events_add_cheer_type.sql"
)


def _check_constraint_values(sql: str) -> set[str]:
    """Pull the ``event_type IN ('a', 'b', ...)`` literal list from a migration."""
    inner = re.search(r"event_type IN \(([^)]+)\)", sql).group(1)
    return set(re.findall(r"'([^']+)'", inner))


@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
class TestCatalogConsistency:
    def test_listener_exists(self, event):
        name = _LISTENER_BY_KEY[event.key]
        assert callable(getattr(EventsComponent, name, None)), (
            f"{event.key}: EventsComponent.{name} listener missing"
        )

    def test_subscription_class_has_factory(self, event):
        if event.subscription_class is None:
            pytest.skip(f"{event.key}: no live subscription (known gap)")
        assert event.subscription_class in _CATALOG_FACTORIES
        assert hasattr(eventsub, event.subscription_class)

    def test_in_migration_check_constraint(self, event):
        sql = _MIGRATION_053.read_text(encoding="utf-8")
        allowed = re.search(r"event_type IN \(([^)]+)\)", sql).group(1)
        assert f"'{event.key}'" in allowed

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
        eventsub.ChannelFollowSubscription(broadcaster_user_id=bc, moderator_user_id=bot),
        eventsub.ChannelSubscribeSubscription(broadcaster_user_id=bc),
        eventsub.ChannelSubscribeMessageSubscription(broadcaster_user_id=bc),
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

_VAR_RE = re.compile(r"\$\((\w+)\)")


@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
class TestCatalogSchema:
    def test_default_template_uses_only_declared_variables(self, event):
        used = set(_VAR_RE.findall(event.default_template))
        declared = {v.name for v in event.variables}
        assert used <= declared, f"{event.key}: template uses undeclared {used - declared}"

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
    assert list(EVENT_KEYS) == ["follow", "subscribe", "resub", "gift_sub", "bits", "raid"]


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


def _fake_payload(key: str) -> MagicMock:
    p = MagicMock()
    if key == "follow":
        p.user.display_name, p.user.name, p.user.id = "Follower", "follower", "u1"
        p.broadcaster.name, p.broadcaster.id = "bc", "ch"
        p.followed_at = datetime.now(UTC)
    elif key == "subscribe":
        p.user.display_name, p.user.name, p.user.id = "Sub", "sub", "u1"
        p.broadcaster.name, p.broadcaster.id = "bc", "ch"
        p.tier, p.gift = "1000", False
    elif key == "resub":
        p.user.display_name, p.user.name, p.user.id = "Re", "re", "u1"
        p.broadcaster.name, p.broadcaster.id = "bc", "ch"
        p.tier, p.months, p.streak_months, p.cumulative_months = "2000", 3, 2, 10
        p.text = "yay"
    elif key == "gift_sub":
        p.broadcaster.name, p.broadcaster.id = "bc", "ch"
        p.anonymous = False
        p.user.display_name, p.user.name, p.user.id = "Gifter", "gifter", "u1"
        p.tier, p.total, p.cumulative_total = "1000", 5, 20
    elif key == "bits":
        p.anonymous = False
        p.user.display_name, p.user.name, p.user.id = "Cheerer", "cheerer", "u1"
        p.broadcaster.name, p.broadcaster.id = "bc", "ch"
        p.bits, p.message = 100, "pog"
    elif key == "raid":
        p.from_broadcaster.display_name, p.from_broadcaster.name = "Raider", "raider"
        p.from_broadcaster.id = "r1"
        p.to_broadcaster.name, p.to_broadcaster.id = "bc", "ch"
        p.to_broadcaster.send_shoutout = AsyncMock()
        p.viewer_count = 42
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
async def test_notify_variables_match_catalog(event):
    comp, _bot = _driver_component()
    listener = getattr(comp, _LISTENER_BY_KEY[event.key])

    await listener(_fake_payload(event.key))

    comp._notify.assert_awaited_once()
    args = comp._notify.await_args.args
    assert args[1] == event.key
    assert set(args[2]) == {v.name for v in event.variables}, (
        f"{event.key}: listener passed {set(args[2])}, catalog declares "
        f"{ {v.name for v in event.variables} }"
    )


@pytest.mark.asyncio
async def test_gift_recipient_gets_no_subscribe_greeting():
    comp, bot = _driver_component()
    payload = _fake_payload("subscribe")
    payload.gift = True

    await comp.event_subscription(payload)

    comp._notify.assert_not_awaited()
    # status is still recorded for the recipient
    bot.analytics.upsert_viewer_subscription.assert_awaited_once()
