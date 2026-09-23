"""Allowlisted community overlay event schemas and payload validation."""

from __future__ import annotations

import re
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

_COLLECTION_KEY = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _collection_error(detail: str) -> ValueError:
    return ValueError(f"Invalid collection snapshot: {detail}")


def _mapping_field(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    nested = value.get(field)
    if not isinstance(nested, Mapping):
        raise _collection_error(f"{field} must be an object")
    return nested


def _positive_int(value: Mapping[str, Any], field: str) -> int:
    candidate = value.get(field)
    if type(candidate) is not int or candidate <= 0:
        raise _collection_error(f"{field} must be a positive integer")
    return candidate


def _bounded_int(value: Mapping[str, Any], field: str, *, minimum: int, maximum: int) -> int:
    candidate = value.get(field)
    if type(candidate) is not int or not minimum <= candidate <= maximum:
        raise _collection_error(f"{field} must be between {minimum} and {maximum}")
    return candidate


def _text_field(value: Mapping[str, Any], field: str, *, maximum: int, key: bool = False) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not 1 <= len(candidate) <= maximum:
        raise _collection_error(f"{field} must be non-empty text up to {maximum} characters")
    if key and _COLLECTION_KEY.fullmatch(candidate) is None:
        raise _collection_error(f"{field} must be a kebab-case key")
    return candidate


def _validate_artwork_url(value: object, field: str) -> None:
    if value is None:
        return
    if (
        not isinstance(value, str)
        or not value.startswith("/images/collections/")
        or ".." in value
        or len(value) > 500
    ):
        raise _collection_error(f"card.artwork.{field} must be a safe same-origin path or null")


def _validate_collection_snapshot(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _collection_error("collection must be an object")

    _positive_int(value, "draw_id")
    _positive_int(value, "pool_revision_id")
    _text_field(value, "algorithm_version", maximum=64, key=True)

    card = _mapping_field(value, "card")
    _positive_int(card, "id")
    _positive_int(card, "revision_id")
    _text_field(card, "key", maximum=64, key=True)
    _text_field(card, "number", maximum=16)
    _text_field(card, "name", maximum=100)
    artwork = _mapping_field(card, "artwork")
    for field in ("portrait_url", "square_url", "backdrop_url"):
        if field not in artwork:
            raise _collection_error(f"card.artwork.{field} is required")
        _validate_artwork_url(artwork[field], field)

    collection_set = _mapping_field(value, "set")
    _positive_int(collection_set, "id")
    _text_field(collection_set, "key", maximum=64, key=True)
    _text_field(collection_set, "name", maximum=100)

    rarity = _mapping_field(value, "rarity")
    _text_field(rarity, "key", maximum=64, key=True)
    _text_field(rarity, "label", maximum=40)
    _bounded_int(rarity, "rank", minimum=1, maximum=32_767)
    _bounded_int(rarity, "effect_intensity", minimum=0, maximum=100)

    is_new = value.get("is_new")
    if type(is_new) is not bool:
        raise _collection_error("is_new must be a boolean")
    copy_count = _positive_int(value, "copy_count")
    if is_new is not (copy_count == 1):
        raise _collection_error("is_new must match whether copy_count is one")

    progress = _mapping_field(value, "progress")
    owned_copies = _positive_int(progress, "owned_copies")
    unique_cards = _positive_int(progress, "unique_cards")
    total_cards = _positive_int(progress, "total_cards")
    if unique_cards > total_cards:
        raise _collection_error("progress.unique_cards cannot exceed total_cards")
    if unique_cards > owned_copies:
        raise _collection_error("progress.unique_cards cannot exceed owned_copies")
    if copy_count > owned_copies:
        raise _collection_error("copy_count cannot exceed progress.owned_copies")
    if unique_cards > owned_copies - copy_count + 1:
        raise _collection_error("progress.unique_cards is impossible for the selected copy_count")

    if "owned_cards" not in value:
        return
    owned_cards = value["owned_cards"]
    if not isinstance(owned_cards, list) or not owned_cards:
        raise _collection_error("owned_cards must be a non-empty list")

    seen_card_ids: set[int] = set()
    seen_card_numbers: set[str] = set()
    inventory_copy_count = 0
    selected_inventory_item: Mapping[str, Any] | None = None
    for index, item_value in enumerate(owned_cards):
        if not isinstance(item_value, Mapping):
            raise _collection_error(f"owned_cards[{index}] must be an object")
        item_card = _mapping_field(item_value, "card")
        item_card_id = _positive_int(item_card, "id")
        _positive_int(item_card, "revision_id")
        _text_field(item_card, "key", maximum=64, key=True)
        item_card_number = _text_field(item_card, "number", maximum=16)
        _text_field(item_card, "name", maximum=100)
        item_artwork = _mapping_field(item_card, "artwork")
        for field in ("portrait_url", "square_url", "backdrop_url"):
            if field not in item_artwork:
                raise _collection_error(f"owned_cards[{index}].card.artwork.{field} is required")
            _validate_artwork_url(item_artwork[field], field)

        item_rarity = _mapping_field(item_value, "rarity")
        _text_field(item_rarity, "key", maximum=64, key=True)
        _text_field(item_rarity, "label", maximum=40)
        _bounded_int(item_rarity, "rank", minimum=1, maximum=32_767)
        _bounded_int(item_rarity, "effect_intensity", minimum=0, maximum=100)
        item_copy_count = _positive_int(item_value, "copy_count")

        if item_card_id in seen_card_ids or item_card_number in seen_card_numbers:
            raise _collection_error("owned_cards must contain unique cards and catalog numbers")
        seen_card_ids.add(item_card_id)
        seen_card_numbers.add(item_card_number)
        inventory_copy_count += item_copy_count
        if item_card_id == card["id"]:
            selected_inventory_item = item_value

    if len(owned_cards) != unique_cards:
        raise _collection_error("owned_cards length must match progress.unique_cards")
    if inventory_copy_count != owned_copies:
        raise _collection_error("owned_cards copy total must match progress.owned_copies")
    if selected_inventory_item is None:
        raise _collection_error("owned_cards must include the selected card")
    if selected_inventory_item["copy_count"] != copy_count:
        raise _collection_error("selected owned card count must match copy_count")
    if selected_inventory_item["card"] != card or selected_inventory_item["rarity"] != rarity:
        raise _collection_error("selected owned card must match the top-level card and rarity")


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
    if event_type == CHECKIN_RECORDED.event_type and "collection" in payload:
        _validate_collection_snapshot(payload["collection"])
