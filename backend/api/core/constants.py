"""Shared constants for the API service."""

VALID_ROLES: frozenset[str] = frozenset(
    {"everyone", "subscriber", "vip", "moderator", "broadcaster"}
)
