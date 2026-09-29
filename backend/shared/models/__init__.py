"""Shared data models for all Niibot backend services."""

from .attendance import (
    CheckinOutcome,
    CheckinReply,
    CheckinResult,
    CheckinSettings,
    CheckinStatus,
    CheckinUnavailable,
    CommunityOverlayAccess,
    CommunityOverlayEvent,
    CommunityOverlayFeed,
)
from .birthday import Birthday, BirthdaySettings
from .channel import Channel, DiscordUser, Token
from .collection import (
    CollectionCardRevision,
    CollectionDraw,
    CollectionProgress,
    CollectionSet,
    DrawPoolRarity,
    DrawPoolRevision,
    DrawSelection,
    RarityRevision,
)
from .roleplay import RoleplayRevision, RoleplaySet

__all__ = [
    "Birthday",
    "BirthdaySettings",
    "CheckinOutcome",
    "CheckinReply",
    "CheckinResult",
    "CheckinSettings",
    "CheckinStatus",
    "CheckinUnavailable",
    "Channel",
    "CollectionCardRevision",
    "CollectionDraw",
    "CollectionProgress",
    "CollectionSet",
    "CommunityOverlayAccess",
    "CommunityOverlayEvent",
    "CommunityOverlayFeed",
    "DiscordUser",
    "DrawPoolRarity",
    "DrawPoolRevision",
    "DrawSelection",
    "RarityRevision",
    "RoleplayRevision",
    "RoleplaySet",
    "Token",
]
