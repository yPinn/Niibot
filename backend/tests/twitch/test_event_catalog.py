"""Consistency tests for the event catalog (shared.events.EVENT_CATALOG).

The point of the catalog is that adding an event type in one layer but not the
others fails loudly here instead of silently never firing (which is exactly how
resub / gift_sub shipped broken). Each catalog entry is checked against:

- the twitchio EventSub factory map in twitch.core.subscriptions
- the twitchio listener method on EventComponent
- the event_configs CHECK constraint (migration 053)
- the DEFAULT_TEMPLATES / DEFAULT_ENABLED seed dicts

Plus: shared.events must not drag twitchio into the api / discord services, and
get_channel_subscriptions must still produce exactly today's subscription set.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from twitch.components.events import EventComponent
from twitch.core.subscriptions import _CATALOG_FACTORIES, get_channel_subscriptions
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


@pytest.mark.parametrize("event", EVENT_CATALOG, ids=lambda e: e.key)
class TestCatalogConsistency:
    def test_listener_exists(self, event):
        name = _LISTENER_BY_KEY[event.key]
        assert callable(getattr(EventComponent, name, None)), (
            f"{event.key}: EventComponent.{name} listener missing"
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


def test_get_channel_subscriptions_is_unchanged():
    """No-op guard: the derived list must equal the pre-refactor hardcoded 13."""
    bc, bot = "bc-1", "bot-1"
    expected = [
        eventsub.ChatMessageSubscription(broadcaster_user_id=bc, user_id=bot),
        eventsub.StreamOnlineSubscription(broadcaster_user_id=bc),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=bc),
        eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=bc),
        eventsub.ChannelFollowSubscription(broadcaster_user_id=bc, moderator_user_id=bot),
        eventsub.ChannelSubscribeSubscription(broadcaster_user_id=bc),
        eventsub.ChannelCheerSubscription(broadcaster_user_id=bc),
        eventsub.ChannelRaidSubscription(to_broadcaster_user_id=bc),
        eventsub.SharedChatSessionBeginSubscription(broadcaster_user_id=bc),
        eventsub.SharedChatSessionUpdateSubscription(broadcaster_user_id=bc),
        eventsub.SharedChatSessionEndSubscription(broadcaster_user_id=bc),
        eventsub.ChannelModeratorAddSubscription(broadcaster_user_id=bc),
        eventsub.ChannelModeratorRemoveSubscription(broadcaster_user_id=bc),
    ]
    got = get_channel_subscriptions(bc, bot)
    assert {_key(s) for s in got} == {_key(s) for s in expected}
    assert len(got) == len(expected)
