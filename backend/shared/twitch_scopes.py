"""Single source of truth for Twitch OAuth scopes and product capabilities.

BOT_SCOPES      — scopes the bot account needs (`nb twitch oauth --role bot`)
BROADCASTER_SCOPES — minimum scopes the streamer grants to authorise the bot

Design principle (master-slave): the bot does everything as itself or as a
moderator. The broadcaster only grants a scope when Twitch *forces* the
operation onto the broadcaster's own account (channel points, subscriptions,
bits, VIP/moderator management). Anything a moderator token can do lives in
BOT_SCOPES, not here — see `moderator:read:followers` / `moderator:read:chatters`.

``BOT_SCOPES`` / ``BROADCASTER_SCOPES`` remain the complete scope sets requested
for a new authorization so existing production capabilities do not regress.
They are deliberately *not* the definition of credential validity: only the
small runtime-core subsets can make the whole credential unusable.  Every
other scope locks one capability and leaves unrelated features available.

The lists are ordered by logical category so frontend grouping is predictable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TwitchCredential = Literal["bot", "broadcaster"]

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
    # channel info (title/game/tags/stream markers — Modify Channel Information
    # and Create Stream Marker both require the broadcaster's own token)
    "channel:manage:broadcast",
    # revenue (Bits API + channel.cheer EventSub require the broadcaster)
    "bits:read",
]

# These are the only missing scopes that make the basic EventSub chat runtime
# impossible. Feature scopes below must never be promoted to global reauth.
BOT_CORE_SCOPES: list[str] = ["user:bot", "user:read:chat", "user:write:chat"]
BROADCASTER_CORE_SCOPES: list[str] = ["channel:bot"]


@dataclass(frozen=True, slots=True)
class TwitchCapability:
    """One user-visible capability and the credential grant it depends on."""

    key: str
    credential: TwitchCredential
    scopes: tuple[str, ...]
    label: str
    core: bool = False


TWITCH_CAPABILITIES: dict[str, TwitchCapability] = {
    # Runtime core. Chat EventSub requires grants from both identities.
    "bot_chat": TwitchCapability("bot_chat", "bot", tuple(BOT_CORE_SCOPES), "Bot 聊天", core=True),
    "broadcaster_chat": TwitchCapability(
        "broadcaster_chat",
        "broadcaster",
        tuple(BROADCASTER_CORE_SCOPES),
        "頻道聊天",
        core=True,
    ),
    # Bot-account feature grants.
    "bot_emotes": TwitchCapability("bot_emotes", "bot", ("user:read:emotes",), "Bot 表情符號"),
    "bot_subscription_status": TwitchCapability(
        "bot_subscription_status",
        "bot",
        ("user:read:subscriptions",),
        "Bot 訂閱狀態",
    ),
    "bot_whispers": TwitchCapability("bot_whispers", "bot", ("user:manage:whispers",), "Bot 私訊"),
    "followers": TwitchCapability("followers", "bot", ("moderator:read:followers",), "追隨事件"),
    "chatters": TwitchCapability("chatters", "bot", ("moderator:read:chatters",), "聊天室名單"),
    "announcements": TwitchCapability(
        "announcements",
        "bot",
        ("moderator:manage:announcements",),
        "公告",
    ),
    "shoutouts": TwitchCapability("shoutouts", "bot", ("moderator:manage:shoutouts",), "Shoutout"),
    "banned_users": TwitchCapability(
        "banned_users",
        "bot",
        ("moderator:manage:banned_users",),
        "封鎖與逾時",
    ),
    # Broadcaster-account feature grants.
    "channel_points": TwitchCapability(
        "channel_points",
        "broadcaster",
        ("channel:read:redemptions",),
        "Channel Points",
    ),
    "subscriptions": TwitchCapability(
        "subscriptions",
        "broadcaster",
        ("channel:read:subscriptions",),
        "訂閱事件",
    ),
    "moderator_management": TwitchCapability(
        "moderator_management",
        "broadcaster",
        ("channel:manage:moderators",),
        "MOD 管理",
    ),
    "vip_management": TwitchCapability(
        "vip_management", "broadcaster", ("channel:manage:vips",), "VIP 管理"
    ),
    "channel_info": TwitchCapability(
        "channel_info",
        "broadcaster",
        ("channel:manage:broadcast",),
        "頻道資訊",
    ),
    "cheers": TwitchCapability("cheers", "broadcaster", ("bits:read",), "Cheer"),
    # Optional real-time acceleration for the default-off Twitch MOD sync.
    # Get Moderators itself can use channel:manage:moderators; only these
    # EventSub topics require moderation:read.
    "moderator_sync_realtime": TwitchCapability(
        "moderator_sync_realtime",
        "broadcaster",
        ("moderation:read",),
        "Twitch MOD 即時同步",
    ),
}


def required_core_scopes(credential: TwitchCredential) -> frozenset[str]:
    """Scopes whose absence makes the whole credential unusable."""
    if credential == "bot":
        return frozenset(BOT_CORE_SCOPES)
    return frozenset(BROADCASTER_CORE_SCOPES)


def missing_capability_scopes(
    capability_key: str, scopes: list[str] | set[str] | frozenset[str]
) -> list[str]:
    """Return only the grants missing for one named product capability."""
    capability = TWITCH_CAPABILITIES[capability_key]
    granted = set(scopes)
    return [scope for scope in capability.scopes if scope not in granted]


def capability_available(
    capability_key: str, scopes: list[str] | set[str] | frozenset[str]
) -> bool:
    return not missing_capability_scopes(capability_key, scopes)


def missing_bot_core_scopes(scopes: list[str] | set[str]) -> list[str]:
    granted = set(scopes)
    return [scope for scope in BOT_CORE_SCOPES if scope not in granted]


def missing_broadcaster_core_scopes(scopes: list[str] | set[str]) -> list[str]:
    granted = set(scopes)
    return [scope for scope in BROADCASTER_CORE_SCOPES if scope not in granted]


def missing_broadcaster_scopes(scopes: list[str] | set[str]) -> list[str]:
    """Full OAuth-request diff for diagnostics, never global health policy."""
    return [s for s in BROADCASTER_SCOPES if s not in scopes]
