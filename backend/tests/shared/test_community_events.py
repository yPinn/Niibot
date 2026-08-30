"""Tests for the allowlisted community renderer event catalog."""

import pytest

from shared.community_events import validate_community_event


def test_accepts_known_complete_payload():
    validate_community_event(
        "checkin.recorded",
        1,
        {"total_days": 3, "checkin_date": "2026-08-30"},
    )


def test_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="Unknown community event schema"):
        validate_community_event("checkin.recorded", 2, {})


def test_rejects_missing_renderer_field():
    with pytest.raises(ValueError, match="checkin_date"):
        validate_community_event("checkin.recorded", 1, {"total_days": 3})
