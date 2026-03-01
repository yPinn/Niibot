"""Unit tests for twitch.core.guards — has_role, is_on_cooldown, record_cooldown."""

from datetime import UTC, datetime, timedelta

from twitch.core.guards import (
    ROLE_HIERARCHY,
    _cooldown_tracker,
    has_role,
    is_on_cooldown,
    record_cooldown,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_chatter(
    *,
    broadcaster: bool = False,
    moderator: bool = False,
    vip: bool = False,
    subscriber: bool = False,
):
    """Return a minimal chatter-like object."""

    class _Chatter:
        broadcaster: bool
        moderator: bool
        vip: bool
        subscriber: bool

    c = _Chatter()
    c.broadcaster = broadcaster
    c.moderator = moderator
    c.vip = vip
    c.subscriber = subscriber
    return c


def make_cooldown_config(cooldown: int | None):
    """Return a minimal config-like object with a cooldown field."""

    class _Config:
        cooldown: int | None

    c = _Config()
    c.cooldown = cooldown
    return c


# ---------------------------------------------------------------------------
# has_role
# ---------------------------------------------------------------------------


class TestHasRole:
    def test_everyone_always_passes(self):
        chatter = make_chatter()
        assert has_role(chatter, "everyone") is True

    def test_broadcaster_passes_broadcaster_check(self):
        chatter = make_chatter(broadcaster=True)
        assert has_role(chatter, "broadcaster") is True

    def test_non_broadcaster_fails_broadcaster_check(self):
        chatter = make_chatter(moderator=True)
        assert has_role(chatter, "broadcaster") is False

    def test_moderator_passes_moderator_check(self):
        chatter = make_chatter(moderator=True)
        assert has_role(chatter, "moderator") is True

    def test_non_moderator_fails_moderator_check(self):
        chatter = make_chatter(subscriber=True)
        assert has_role(chatter, "moderator") is False

    def test_vip_passes_vip_check(self):
        chatter = make_chatter(vip=True)
        assert has_role(chatter, "vip") is True

    def test_subscriber_fails_vip_check(self):
        chatter = make_chatter(subscriber=True)
        assert has_role(chatter, "vip") is False

    def test_subscriber_passes_subscriber_check(self):
        chatter = make_chatter(subscriber=True)
        assert has_role(chatter, "subscriber") is True

    def test_non_subscriber_fails_subscriber_check(self):
        chatter = make_chatter()
        assert has_role(chatter, "subscriber") is False

    def test_moderator_passes_vip_check(self):
        # Moderator outranks VIP
        chatter = make_chatter(moderator=True)
        assert has_role(chatter, "vip") is True

    def test_moderator_passes_subscriber_check(self):
        chatter = make_chatter(moderator=True)
        assert has_role(chatter, "subscriber") is True

    def test_broadcaster_passes_all_roles(self):
        chatter = make_chatter(broadcaster=True)
        for role in ROLE_HIERARCHY:
            assert has_role(chatter, role) is True

    def test_unknown_role_treated_as_everyone(self):
        # Unknown role falls back to min_level 0, which only non-0 roles fail.
        # ROLE_HIERARCHY.index raises ValueError — treated as 0 (everyone).
        chatter = make_chatter()
        # "wizard" not in hierarchy → treated as everyone (min_level = 0) → passes
        assert has_role(chatter, "wizard") is True


# ---------------------------------------------------------------------------
# is_on_cooldown / record_cooldown
# ---------------------------------------------------------------------------


class TestCooldown:
    def setup_method(self):
        """Clear any leaked state from prior tests."""
        _cooldown_tracker.clear()

    def test_no_cooldown_config_not_on_cooldown(self):
        cfg = make_cooldown_config(cooldown=0)
        assert is_on_cooldown("ch1", "cmd1", cfg, None) is False

    def test_none_cooldown_uses_channel_default(self):
        from shared.models.channel import Channel

        ch = Channel(channel_id="ch2", channel_name="test", default_cooldown=30)
        cfg = make_cooldown_config(cooldown=None)
        record_cooldown("ch2", "cmd2")
        assert is_on_cooldown("ch2", "cmd2", cfg, ch) is True

    def test_none_cooldown_no_channel_not_on_cooldown(self):
        cfg = make_cooldown_config(cooldown=None)
        # No channel → effective cooldown 0 → not on cooldown
        assert is_on_cooldown("ch3", "cmd3", cfg, None) is False

    def test_freshly_recorded_is_on_cooldown(self):
        cfg = make_cooldown_config(cooldown=30)
        record_cooldown("ch4", "cmd4")
        assert is_on_cooldown("ch4", "cmd4", cfg, None) is True

    def test_expired_cooldown_not_on_cooldown(self):
        cfg = make_cooldown_config(cooldown=10)
        # Manually set timestamp far in the past (UTC-aware, matching guards.py)
        _cooldown_tracker["ch5:cmd5"] = datetime.now(UTC) - timedelta(seconds=60)
        assert is_on_cooldown("ch5", "cmd5", cfg, None) is False

    def test_record_then_check_boundary(self):
        cfg = make_cooldown_config(cooldown=5)
        record_cooldown("ch6", "cmd6")
        # Just recorded → still on cooldown
        assert is_on_cooldown("ch6", "cmd6", cfg, None) is True

    def test_different_channels_independent(self):
        cfg = make_cooldown_config(cooldown=30)
        record_cooldown("ch7", "same_cmd")
        # ch7 is on cooldown, ch8 is not
        assert is_on_cooldown("ch7", "same_cmd", cfg, None) is True
        assert is_on_cooldown("ch8", "same_cmd", cfg, None) is False

    def test_different_commands_same_channel_independent(self):
        cfg = make_cooldown_config(cooldown=30)
        record_cooldown("ch9", "cmd_a")
        assert is_on_cooldown("ch9", "cmd_a", cfg, None) is True
        assert is_on_cooldown("ch9", "cmd_b", cfg, None) is False

    def test_command_cooldown_overrides_channel_default(self):
        from shared.models.channel import Channel

        ch = Channel(channel_id="ch10", channel_name="test", default_cooldown=60)
        # Command-level cooldown = 0 overrides channel default of 60
        cfg = make_cooldown_config(cooldown=0)
        record_cooldown("ch10", "free_cmd")
        assert is_on_cooldown("ch10", "free_cmd", cfg, ch) is False
