"""Shared constants for the API service."""

VALID_ROLES: frozenset[str] = frozenset(
    {"everyone", "subscriber", "vip", "moderator", "broadcaster"}
)

# Twitch drops anything past 500 characters in a chat message. Responses are
# stored as templates, so the stored text must leave room for the variables to
# expand at send time — $(user) alone can add ~25 characters.
MAX_RESPONSE_LENGTH: int = 450
