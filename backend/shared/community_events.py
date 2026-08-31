"""Allowlisted community overlay event schemas and payload validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CommunityEventSpec:
    event_type: str
    schema_version: int
    required_payload: frozenset[str]


CHECKIN_RECORDED = CommunityEventSpec(
    event_type="checkin.recorded",
    schema_version=1,
    required_payload=frozenset({"total_days", "checkin_date"}),
)

TAROT_DRAWN = CommunityEventSpec(
    event_type="tarot.drawn",
    schema_version=1,
    required_payload=frozenset(
        {
            "card_id",
            "card_name",
            "card_name_en",
            "orientation",
            "orientation_label",
            "category",
            "category_label",
            "keywords",
            "meaning",
            "advice",
            "image_path",
            "deck_id",
            "deck_version",
        }
    ),
)

COMMUNITY_EVENT_CATALOG = {
    (CHECKIN_RECORDED.event_type, CHECKIN_RECORDED.schema_version): CHECKIN_RECORDED,
    (TAROT_DRAWN.event_type, TAROT_DRAWN.schema_version): TAROT_DRAWN,
}


def validate_community_event(
    event_type: str,
    schema_version: int,
    payload: Mapping[str, Any],
) -> None:
    """Reject unknown event versions and incomplete renderer payloads."""
    spec = COMMUNITY_EVENT_CATALOG.get((event_type, schema_version))
    if spec is None:
        raise ValueError(f"Unknown community event schema: {event_type}.v{schema_version}")
    missing = spec.required_payload.difference(payload)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Missing community event payload fields: {names}")
