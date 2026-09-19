"""Admin-only API routes — accessible only to the bot owner.

Docker log access, the ad-hoc DB query endpoint, and global module config live
in the ``routers.admin`` sub-package and are mounted onto this router below.
"""

import asyncio
import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.config import get_settings
from core.dependencies import (
    get_admission_service,
    get_channel_service,
    get_current_user_id,
    get_db_pool,
    get_twitch_api,
    require_owner,
)
from routers.admin.client_errors import router as _client_errors_router
from routers.admin.db import _json_safe  # noqa: F401  re-exported for tests
from routers.admin.db import router as _db_router
from routers.admin.logs import _parse_docker_stream  # noqa: F401  re-exported for tests
from routers.admin.logs import router as _logs_router
from routers.admin.modules import router as _modules_router
from services import AdmissionService, ChannelService, TwitchAPIClient
from services.emote_sync import (
    EmoteItem,
    available_emote_names,
    bot_tokens_for,
    fetch_channel_emotes,
    resolve_bot_ids,
    sync_enabled_emotes,
    to_emote_items,
)
from shared.errors import ChannelNotFoundError, InvalidInputError, NotFoundError
from shared.repositories.activation_code import ActivationCodeRepository
from shared.repositories.channel import ChannelRepository
from shared.twitch_scopes import BOT_SCOPES
from shared.twitch_scopes import BROADCASTER_SCOPES as _BROADCASTER_SCOPES

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminBotNotConfiguredError(NotFoundError):
    code = "ADMIN.BOT_NOT_CONFIGURED"
    user_message = "機器人帳號尚未設定"


class ActivationCodeNotFoundError(NotFoundError):
    code = "ADMIN.CODE_NOT_FOUND"
    user_message = "找不到可撤銷的啟用碼"


class MembershipNotFoundError(NotFoundError):
    code = "ADMIN.MEMBERSHIP_NOT_FOUND"
    user_message = "找不到這名使用者的會員資料"


class AdminInvalidError(InvalidInputError):
    code = "ADMIN.INVALID"
    user_message = "輸入的內容有誤，請檢查後再試"


router.include_router(_logs_router)
router.include_router(_db_router)
router.include_router(_modules_router)
router.include_router(_client_errors_router)


def _scope_diff(stored_str: str | None, required: list[str]) -> tuple[list[str], list[str]]:
    """Returns (granted_scopes, missing_scopes) relative to the required list."""
    stored = set(stored_str.split()) if stored_str else set()
    granted = [s for s in required if s in stored]
    missing = [s for s in required if s not in stored]
    return granted, missing


async def _check_channel(
    channel_id: str,
    *,
    bot_id: str,
    channel_service: ChannelService,
    twitch_api: TwitchAPIClient,
    repo: ChannelRepository,
) -> tuple[str, str, list[str], list[str]]:
    if not bot_id:
        return channel_id, "token_error", [], list(_BROADCASTER_SCOPES)
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        return channel_id, "token_error", [], list(_BROADCASTER_SCOPES)
    token_obj = await repo.get_token(channel_id, "broadcaster")
    granted, missing = _scope_diff(token_obj.scopes if token_obj else None, _BROADCASTER_SCOPES)
    status = await twitch_api.get_bot_mod_status(channel_id, bot_id, token)
    return channel_id, status, granted, missing


class AdminChannelInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    offline_image_url: str
    is_live: bool
    is_enabled: bool
    mod_status: str  # 'mod' | 'no_mod' | 'token_error' | 'scope_error'
    is_bot: bool
    granted_scopes: list[str]
    missing_scopes: list[str]
    membership_status: str  # 'active' | 'pending' | 'suspended'
    membership_reason: str | None
    owner_user_id: str | None


class BotTokenInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    status: str  # 'ok' | 'missing' | 'no_token'
    granted_scopes: list[str]
    missing_scopes: list[str]


@router.get("/bot-status", response_model=BotTokenInfo)
async def get_bot_status(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> BotTokenInfo:
    """Return bot account's own token scope status. Owner-only."""
    bot_id = get_settings().bot_id or ""
    if not bot_id:
        raise AdminBotNotConfiguredError()

    repo = ChannelRepository(pool)
    token_obj, users = await asyncio.gather(
        repo.get_token(bot_id, "bot"),
        twitch_api.get_users_by_ids([bot_id]),
    )
    user = users[0] if users else {}

    if not token_obj:
        return BotTokenInfo(
            id=bot_id,
            name=user.get("login", ""),
            display_name=user.get("display_name", ""),
            avatar=user.get("profile_image_url", ""),
            status="no_token",
            granted_scopes=[],
            missing_scopes=list(BOT_SCOPES),
        )

    granted, missing = _scope_diff(token_obj.scopes, BOT_SCOPES)
    return BotTokenInfo(
        id=bot_id,
        name=user.get("login", ""),
        display_name=user.get("display_name", ""),
        avatar=user.get("profile_image_url", ""),
        status="ok" if not missing else "missing",
        granted_scopes=granted,
        missing_scopes=missing,
    )


@router.get("/channels", response_model=list[AdminChannelInfo])
async def get_admin_channels(
    owner_id: str = Depends(require_owner),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: Pool = Depends(get_db_pool),
) -> list[AdminChannelInfo]:
    """Return all monitored channels with mod status and scope breakdown. Owner-only.

    Includes active, pending, and suspended tenants (rejected is excluded — no
    monitoring value) so the owner can see channels awaiting review or that
    were suspended, not just active ones. The frontend buckets by
    ``membership_status`` rather than ``is_enabled``, since a non-active owner's
    channel is always disabled regardless of why (084's trigger), which would
    otherwise be indistinguishable from an active owner who manually paused it.
    """
    repo_all = ChannelRepository(pool)
    bot_id = get_settings().bot_id or ""
    all_channels = await repo_all.list_all_channels()
    status_map = await repo_all.list_monitored_owner_channel_status()
    other = [
        ch
        for ch in all_channels
        if ch.channel_id != owner_id and (ch.channel_id == bot_id or ch.channel_id in status_map)
    ]
    if not other:
        return []

    channel_ids = [ch.channel_id for ch in other]
    enabled_set = {ch.channel_id for ch in other if ch.enabled}
    repo = ChannelRepository(pool)

    users_data, streams_data = await asyncio.gather(
        twitch_api.get_users_by_ids(channel_ids),
        twitch_api.get_streams(channel_ids),
    )
    live_ids = {s["user_id"] for s in streams_data}
    user_map = {u["id"]: u for u in users_data}

    raw = await asyncio.gather(
        *[
            _check_channel(
                cid,
                bot_id=bot_id,
                channel_service=channel_service,
                twitch_api=twitch_api,
                repo=repo,
            )
            for cid in channel_ids
        ],
        return_exceptions=True,
    )
    channel_data: dict[str, tuple[str, list[str], list[str]]] = {}
    for r in raw:
        if isinstance(r, Exception):
            LOGGER.warning("channel check failed: %s", r)
        else:
            cid, status, granted, missing = r  # type: ignore[misc]
            channel_data[cid] = (status, granted, missing)

    result = []
    for ch in other:
        cid = ch.channel_id
        if cid not in user_map:
            continue
        u = user_map[cid]
        status, granted, missing = channel_data.get(cid, ("error", [], []))
        membership_status, owner_user_id, membership_reason = status_map.get(
            cid, ("active", None, None)
        )
        result.append(
            AdminChannelInfo(
                id=cid,
                name=u.get("login", ""),
                display_name=u.get("display_name", ""),
                avatar=u.get("profile_image_url", ""),
                offline_image_url=u.get("offline_image_url", ""),
                is_live=cid in live_ids,
                is_enabled=cid in enabled_set,
                mod_status=status,
                is_bot=cid == bot_id,
                granted_scopes=granted,
                missing_scopes=missing,
                membership_status=membership_status,
                membership_reason=membership_reason,
                owner_user_id=owner_user_id,
            )
        )

    def _channel_tier(x: AdminChannelInfo) -> int:
        if x.is_bot:
            return 0
        if x.membership_status == "suspended":
            return 7
        if x.membership_status == "pending":
            return 8
        if not x.is_enabled:
            return 6
        if x.mod_status == "mod":
            return 1 if not x.missing_scopes else 2
        if x.mod_status == "no_mod":
            return 3
        if x.mod_status == "scope_error":
            return 4
        return 5  # token_error

    result.sort(key=lambda x: (_channel_tier(x), x.name))
    return result


class GrantInfo(BaseModel):
    id: int
    kind: str
    status: str
    platform_user_id: str | None
    code_plain: str | None
    reward_cost: int | None
    channel_id: str | None
    redemption_id: str | None
    issued_at: datetime
    expires_at: datetime
    used_at: datetime | None
    attempt_count: int
    display_name: str | None
    avatar: str | None
    username: str | None


class GrantKindCounts(BaseModel):
    kind: str
    issued_7d: int
    consumed_7d: int
    issued_30d: int
    consumed_30d: int
    issued_all: int
    consumed_all: int
    outstanding: int


class OnboardingFunnel(BaseModel):
    active_members: int
    by_kind: list[GrantKindCounts]


class OwnerCodeResponse(BaseModel):
    code: str


class ActivationRequestInfo(BaseModel):
    """Legacy shape consumed by the existing admin UI list view.

    `id` is the user's UUID rendered as a string (was previously the integer
    activation_requests.id). `note` is the latest 'requested' event reason or
    an empty string. The frontend was updated to treat id as a string in the
    same release.
    """

    id: str
    platform_user_id: str
    display_name: str | None
    username: str | None
    avatar: str | None
    note: str
    created_at: datetime


class MembershipEventInfo(BaseModel):
    id: int
    event_type: str
    actor_type: str
    actor_user_id: str | None
    reason: str | None
    metadata: dict
    occurred_at: datetime


class MembershipDecisionRequest(BaseModel):
    """Body for approve/reject/suspend/reinstate calls."""

    reason: str = Field(default="", max_length=500)


@router.get("/grants", response_model=list[GrantInfo])
async def list_activation_grants(
    kind: str | None = Query(None),
    status: str | None = Query(None),
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[GrantInfo]:
    """All activation grants (any status / kind), newest first. Owner-only."""
    rows = await ActivationCodeRepository(pool).list_grants(kind=kind, status=status)
    return [GrantInfo(**dict(r)) for r in rows]


@router.post("/grants", response_model=OwnerCodeResponse)
async def create_owner_grant(
    owner_user_id: str = Depends(get_current_user_id),
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> OwnerCodeResponse:
    """Issue an unbound owner_manual activation code. Owner-only.

    The code is a bearer token — whoever types it on /activate is admitted.
    TTL (72h), single use and revoke are the controls.
    """
    code = await ActivationCodeRepository(pool).create_owner_code(issued_by_user_id=owner_user_id)
    LOGGER.info("owner_activation_code_issued")
    return OwnerCodeResponse(code=code)


@router.delete("/grants/{grant_id}")
async def revoke_grant(
    grant_id: int,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Revoke a live (issued) grant by id. Owner-only."""
    if not await ActivationCodeRepository(pool).revoke(grant_id):
        raise ActivationCodeNotFoundError(context={"grant_id": grant_id})
    LOGGER.info("activation_grant_revoked", extra={"grant_id": grant_id})
    return {"revoked": True}


@router.get("/onboarding-funnel", response_model=OnboardingFunnel)
async def get_onboarding_funnel(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> OnboardingFunnel:
    """Redemption→activation conversion per grant kind + active member count."""
    active = await pool.fetchval("SELECT COUNT(*) FROM memberships WHERE status = 'active'")
    rows = await ActivationCodeRepository(pool).funnel_counts()
    return OnboardingFunnel(
        active_members=active or 0,
        by_kind=[GrantKindCounts(**dict(r)) for r in rows],
    )


@router.get("/activation-requests", response_model=list[ActivationRequestInfo])
async def get_activation_requests(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[ActivationRequestInfo]:
    """List pending memberships for owner review. Owner-only.

    Backed by the new memberships + membership_events tables; the response
    shape is preserved so the existing frontend keeps working. The `id`
    field now carries the user's UUID rather than the legacy integer
    activation_requests.id — approve/reject endpoints accept either.
    """
    rows = await pool.fetch(
        """
        SELECT m.user_id::text                                    AS id,
               COALESCE(i.platform_user_id, '')                   AS platform_user_id,
               u.display_name,
               i.username,
               u.avatar,
               COALESCE(
                   (
                       SELECT reason FROM membership_events e
                       WHERE e.user_id = m.user_id
                         AND e.event_type = 'requested'
                       ORDER BY e.occurred_at DESC LIMIT 1
                   ),
                   ''
               )                                                  AS note,
               COALESCE(
                   (
                       SELECT occurred_at FROM membership_events e
                       WHERE e.user_id = m.user_id
                         AND e.event_type = 'requested'
                       ORDER BY e.occurred_at DESC LIMIT 1
                   ),
                   m.updated_at
               )                                                  AS created_at
          FROM memberships m
          JOIN users u ON u.id = m.user_id
     LEFT JOIN identities i
            ON i.user_id = m.user_id AND i.platform = 'twitch'
         WHERE m.status = 'pending'
      ORDER BY created_at ASC
        """
    )
    return [ActivationRequestInfo(**dict(r)) for r in rows]


@router.post("/activation-requests/{user_id}/approve")
async def approve_activation_request(
    user_id: str,
    body: MembershipDecisionRequest | None = None,
    approver_id: str = Depends(get_current_user_id),
    _: str = Depends(require_owner),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Approve a pending membership. Owner-only.

    Body may carry an optional `reason` recorded in membership_events for
    audit. The path param accepts the user's UUID (canonical) or the legacy
    integer request id is no longer supported — frontend was updated.
    """
    try:
        decision = await admission.approve(
            user_id=user_id,
            approver_user_id=approver_id,
            reason=(body.reason if body else "") or "admin_approval",
        )
    except ValueError as e:
        raise MembershipNotFoundError(context={"user_id": user_id}) from e
    LOGGER.info(
        "membership_approved",
        extra={"user_id": user_id, "state_changed": decision.state_changed},
    )
    return {"approved": True}


# ── Bot emote availability (diagnostics + resync) ────────────────────────────


class ChannelEmotes(BaseModel):
    channel_id: str
    name: str
    display_name: str
    avatar: str
    # Which account this row was measured against — once per-channel bot
    # switching ships, different rows may legitimately show different ids.
    bot_user_id: str
    available_count: int
    total_count: int
    # Whether the bot account holds a real subscription to this channel.
    # Authoritative (Check User Subscription) — channel-points emote unlocks do
    # NOT count, unlike emote-availability which they would inflate. False also
    # covers "unknown" (no bot token, or bot token lacks user:read:subscriptions).
    is_subscribed: bool = False
    emotes: list[EmoteItem]


class ResyncResult(BaseModel):
    channel_id: str
    synced: bool
    available_count: int


async def _enabled_tenant_channels(pool: Pool, bot_id: str) -> list:
    """Enabled channels, excluding only the SYSTEM DEFAULT bot's own channel.

    The owner is also a broadcaster, so their own channel is a valid tenant
    where bot emote availability matters — it is intentionally included.

    This exclusion is deliberately kept keyed to the system default id, not
    each channel's per-channel resolved bot id (see resolve_bot_ids below,
    used at fetch time) — a broadcaster who is ALSO someone else's custom bot
    account must not lose their own diagnostics row because of that.
    """
    all_channels = await ChannelRepository(pool).list_all_channels()
    return [ch for ch in all_channels if ch.enabled and ch.channel_id != bot_id]


@router.get("/bot-emotes", response_model=list[ChannelEmotes])
async def get_bot_emotes(
    owner_id: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[ChannelEmotes]:
    """Per-channel view of which channel emotes each channel's current bot
    account can use.

    Aggregated across all enabled tenant channels. Availability is fetched live
    from Twitch (no cache). Global emotes are omitted — they are always usable,
    so they carry no diagnostic signal. Owner-only.
    """
    system_bot_id = get_settings().bot_id or ""
    channels = await _enabled_tenant_channels(pool, system_bot_id)
    if not channels:
        return []

    channel_ids = [ch.channel_id for ch in channels]
    bot_ids = await resolve_bot_ids(pool, channel_ids, system_bot_id=system_bot_id)
    tokens = await bot_tokens_for(pool, bot_ids.values())
    users = await twitch_api.get_users_by_ids(channel_ids)
    user_map = {u["id"]: u for u in users}

    sem = asyncio.Semaphore(5)

    async def _fetch(cid: str) -> tuple[str, str, list[EmoteItem], bool]:
        async with sem:
            bid = bot_ids[cid]
            token = tokens.get(bid)
            fetch = await fetch_channel_emotes(
                twitch_api, cid, bot_id=bid, bot_token=token, include_global=False
            )
            # Authoritative subscription check, independent of emote unlocks.
            is_subscribed = await twitch_api.is_user_subscribed(cid, token, bid) if token else False
            items = to_emote_items(fetch, include_global=False)
            # Usable emotes first, then alphabetical within each group.
            items.sort(key=lambda it: (not it.available, it.name.lower()))
            return cid, bid, items, is_subscribed

    raw = await asyncio.gather(*[_fetch(cid) for cid in channel_ids], return_exceptions=True)

    result: list[ChannelEmotes] = []
    for r in raw:
        if isinstance(r, Exception):
            LOGGER.warning("bot-emotes fetch failed: %s", r)
            continue
        cid, bid, items, is_subscribed = r  # type: ignore[misc]
        u = user_map.get(cid, {})
        result.append(
            ChannelEmotes(
                channel_id=cid,
                name=u.get("login", ""),
                display_name=u.get("display_name", ""),
                avatar=u.get("profile_image_url", ""),
                bot_user_id=bid,
                available_count=sum(1 for it in items if it.available),
                total_count=len(items),
                is_subscribed=is_subscribed,
                emotes=items,
            )
        )

    # Most blocked emotes first (most actionable), then alphabetical.
    result.sort(key=lambda c: (-(c.total_count - c.available_count), c.name))
    return result


@router.post("/bot-emotes/resync", response_model=list[ResyncResult])
async def resync_bot_emotes(
    channel_id: str | None = Query(None),
    owner_id: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[ResyncResult]:
    """Re-query Twitch and write each channel's current bot account's usable
    emotes into enabled_emotes.

    Closes the gap where following or subscribing a channel with the bot account
    does not otherwise trigger a re-sync (only mod changes and visiting a
    channel's emote page do). Pass channel_id to target one channel, or omit
    to resync every enabled tenant channel. Owner-only.
    """
    system_bot_id = get_settings().bot_id or ""
    channels = await _enabled_tenant_channels(pool, system_bot_id)
    if channel_id is not None:
        channels = [ch for ch in channels if ch.channel_id == channel_id]
        if not channels:
            raise ChannelNotFoundError(
                user_message="找不到頻道，或頻道未啟用", context={"channel_id": channel_id}
            )
    if not channels:
        return []

    channel_ids = [ch.channel_id for ch in channels]
    bot_ids = await resolve_bot_ids(pool, channel_ids, system_bot_id=system_bot_id)
    tokens = await bot_tokens_for(pool, bot_ids.values())
    global_raw = await twitch_api.get_global_emotes()
    sem = asyncio.Semaphore(5)

    async def _resync(cid: str) -> ResyncResult:
        async with sem:
            bid = bot_ids[cid]
            token = tokens.get(bid)
            fetch = await fetch_channel_emotes(
                twitch_api, cid, bot_id=bid, bot_token=token, include_global=False
            )
            names = available_emote_names(fetch.channel_raw, global_raw, fetch.accessible)
            synced = await sync_enabled_emotes(pool, cid, names)
            return ResyncResult(channel_id=cid, synced=synced, available_count=len(names))

    raw = await asyncio.gather(*[_resync(cid) for cid in channel_ids], return_exceptions=True)
    results: list[ResyncResult] = []
    for r in raw:
        if isinstance(r, Exception):
            LOGGER.warning("bot-emotes resync failed: %s", r)
            continue
        results.append(r)  # type: ignore[arg-type]

    LOGGER.info(
        "bot_emote_resync",
        extra={
            "channels": len(results),
            "updated": sum(1 for r in results if r.synced),
        },
    )
    return results


@router.post("/activation-requests/{user_id}/reject")
async def reject_activation_request(
    user_id: str,
    body: MembershipDecisionRequest | None = None,
    approver_id: str = Depends(get_current_user_id),
    _: str = Depends(require_owner),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    """Reject a pending membership. Owner-only."""
    try:
        decision = await admission.reject(
            user_id=user_id,
            approver_user_id=approver_id,
            reason=(body.reason if body else "") or "admin_rejection",
        )
    except ValueError as e:
        raise MembershipNotFoundError(context={"user_id": user_id}) from e
    LOGGER.info(
        "membership_rejected",
        extra={"user_id": user_id, "state_changed": decision.state_changed},
    )
    return {"rejected": True}


@router.get(
    "/memberships/{user_id}/timeline",
    response_model=list[MembershipEventInfo],
)
async def get_membership_timeline(
    user_id: str,
    _: str = Depends(require_owner),
    admission: AdmissionService = Depends(get_admission_service),
) -> list[MembershipEventInfo]:
    """Full membership_events history for a user. Owner-only."""
    events = await admission.timeline(user_id, limit=200)
    return [MembershipEventInfo(**event.__dict__) for event in events]


@router.post("/memberships/{user_id}/suspend")
async def suspend_membership(
    user_id: str,
    body: MembershipDecisionRequest,
    approver_id: str = Depends(get_current_user_id),
    _: str = Depends(require_owner),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    reason = body.reason.strip()
    if not reason:
        raise AdminInvalidError(user_message="請填寫停權原因")
    try:
        decision = await admission.suspend(
            user_id=user_id,
            approver_user_id=approver_id,
            reason=reason,
        )
    except ValueError as e:
        raise MembershipNotFoundError(context={"user_id": user_id}) from e
    LOGGER.info("membership_suspended", extra={"user_id": user_id})
    return {"suspended": True, "state_changed": decision.state_changed}


@router.post("/memberships/{user_id}/reinstate")
async def reinstate_membership(
    user_id: str,
    body: MembershipDecisionRequest,
    approver_id: str = Depends(get_current_user_id),
    _: str = Depends(require_owner),
    admission: AdmissionService = Depends(get_admission_service),
) -> dict:
    try:
        decision = await admission.reinstate(
            user_id=user_id,
            approver_user_id=approver_id,
            reason=body.reason or "admin_reinstate",
        )
    except ValueError as e:
        raise MembershipNotFoundError(context={"user_id": user_id}) from e
    LOGGER.info("membership_reinstated", extra={"user_id": user_id})
    return {"reinstated": True, "state_changed": decision.state_changed}
