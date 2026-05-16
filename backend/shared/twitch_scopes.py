"""Single source of truth for Twitch OAuth scopes.

BOT_SCOPES      — scopes the bot account needs (obtained via tw_oauth.py bot)
BROADCASTER_SCOPES — minimum scopes the streamer grants to authorise the bot
"""

BOT_SCOPES: list[str] = [
    "user:bot",
    "user:read:chat",
    "user:write:chat",
    "user:read:emotes",
    "moderator:read:followers",
    "moderator:manage:announcements",
    "moderator:manage:shoutouts",
    "user:manage:whispers",
]

BROADCASTER_SCOPES: list[str] = [
    "channel:bot",
    "channel:read:redemptions",
    "channel:read:subscriptions",
    "channel:manage:moderators",
    "channel:manage:vips",
    "bits:read",
    "moderation:read",
    "moderator:read:followers",
    "moderator:read:chatters",
]
