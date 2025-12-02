"""統一的配置檔案"""

BOT_SCOPES = [
    "user:read:chat",
    "user:write:chat",
    "user:bot",
    "moderator:manage:announcements",
    "user:manage:whispers",
]

BROADCASTER_SCOPES = [
    "channel:bot",
    "user:write:chat",
    "user:manage:whispers",
    "channel:read:redemptions",
    "channel:manage:vips",
    "moderator:manage:announcements",
    "channel:read:subscriptions",
    "channel:read:hype_train",
    "channel:read:polls",
    "channel:read:predictions",
    "bits:read",
]
