"""Immutable collection catalog records and per-check-in draw snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RarityRevision:
    id: int
    key: str
    display_name: str
    sort_rank: int
    effect_intensity: int


@dataclass(frozen=True, slots=True)
class CollectionSet:
    id: int
    key: str
    display_name: str
    total_cards: int


@dataclass(frozen=True, slots=True)
class CollectionCardRevision:
    card_id: int
    revision_id: int
    key: str
    number: str
    name: str
    description: str | None
    collection_set: CollectionSet
    rarity: RarityRevision
    portrait_url: str | None
    square_url: str | None
    backdrop_url: str | None


@dataclass(frozen=True, slots=True)
class DrawPoolRarity:
    rarity: RarityRevision
    weight: int
    cards: tuple[CollectionCardRevision, ...]


@dataclass(frozen=True, slots=True)
class DrawPoolRevision:
    id: int
    algorithm_version: str
    rarities: tuple[DrawPoolRarity, ...]


@dataclass(frozen=True, slots=True)
class DrawSelection:
    pool_revision_id: int
    algorithm_version: str
    card: CollectionCardRevision
    entropy: bytes
    rarity_roll: int
    rarity_weight_total: int
    card_roll: int
    card_bucket_size: int


@dataclass(frozen=True, slots=True)
class CollectionProgress:
    """Progress within the immutable set containing the selected card."""

    owned_copies: int
    unique_cards: int
    total_cards: int


@dataclass(frozen=True, slots=True)
class CollectionDraw:
    id: int
    selection: DrawSelection
    is_new: bool
    copy_count: int
    progress: CollectionProgress

    def to_event_snapshot(self) -> dict[str, object]:
        """Build the presentation-neutral snapshot carried by the overlay event."""
        card = self.selection.card
        return {
            "draw_id": self.id,
            "pool_revision_id": self.selection.pool_revision_id,
            "algorithm_version": self.selection.algorithm_version,
            "card": {
                "id": card.card_id,
                "revision_id": card.revision_id,
                "key": card.key,
                "number": card.number,
                "name": card.name,
                "artwork": {
                    "portrait_url": card.portrait_url,
                    "square_url": card.square_url,
                    "backdrop_url": card.backdrop_url,
                },
            },
            "set": {
                "id": card.collection_set.id,
                "key": card.collection_set.key,
                "name": card.collection_set.display_name,
            },
            "rarity": {
                "key": card.rarity.key,
                "label": card.rarity.display_name,
                "rank": card.rarity.sort_rank,
                "effect_intensity": card.rarity.effect_intensity,
            },
            "is_new": self.is_new,
            "copy_count": self.copy_count,
            "progress": {
                "owned_copies": self.progress.owned_copies,
                "unique_cards": self.progress.unique_cards,
                "total_cards": self.progress.total_cards,
            },
        }
