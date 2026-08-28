"""Single source of truth for Twitch OAuth scopes.

BOT_SCOPES      — scopes the bot account needs (`nb twitch oauth --role bot`)
BROADCASTER_SCOPES — minimum scopes the streamer grants to authorise the bot

Both lists are ordered by logical category so frontend grouping is predictable.
"""

BOT_SCOPES: list[str] = [
    # identity / bot connection
    "user:bot",
    # chat
    "user:read:chat",
    "user:write:chat",
    # user
    "user:read:emotes",
    "user:read:subscriptions",
    "user:manage:whispers",
    # moderation
    "moderator:read:followers",
    "moderator:manage:announcements",
    "moderator:manage:shoutouts",
    "moderator:manage:banned_users",
]

BROADCASTER_SCOPES: list[str] = [
    # identity / bot connection
    "channel:bot",
    # channel data
    "channel:read:redemptions",
    "channel:read:subscriptions",
    # channel management
    "channel:manage:moderators",
    "channel:manage:vips",
    # revenue
    "bits:read",
    # moderation
    "moderation:read",
    "moderator:read:followers",
    "moderator:read:chatters",
]
