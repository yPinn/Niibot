"""Single source of truth for Twitch OAuth scopes.

BOT_SCOPES      — scopes the bot account needs (obtained via tw_oauth.py bot)
BROADCASTER_SCOPES — minimum scopes the streamer grants to authorise the bot

Design principle (master-slave): the bot does everything as itself or as a
moderator. The broadcaster only grants a scope when Twitch *forces* the
operation onto the broadcaster's own account (channel points, subscriptions,
bits, VIP/moderator management). Anything a moderator token can do lives in
BOT_SCOPES, not here — see `moderator:read:followers` / `moderator:read:chatters`.

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
    # moderation (bot acts as a moderator of the channel)
    "moderator:read:followers",
    "moderator:read:chatters",
    "moderator:manage:announcements",
    "moderator:manage:shoutouts",
    "moderator:manage:banned_users",
]

BROADCASTER_SCOPES: list[str] = [
    # identity / bot connection
    "channel:bot",
    # channel data (no moderator-token equivalent — must be the broadcaster)
    "channel:read:redemptions",
    "channel:read:subscriptions",
    # channel management (only the broadcaster can add/remove mods and VIPs)
    "channel:manage:moderators",
    "channel:manage:vips",
    # revenue (Bits API + channel.cheer EventSub require the broadcaster)
    "bits:read",
]
