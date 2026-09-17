"""Import commands from other Twitch chat bots (Nightbot / StreamElements)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from urllib.parse import quote as _url_quote

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import get_db_pool, get_twitch_api, require_activated
from core.dependencies import require_self_tenant_access as _require_tenant
from services import TenantContext, TwitchAPIClient
from services.command_import.models import ImportItem, ImportPreview
from services.command_import.service import (
    CommandImportService,
    PreviewNotFoundError,
    default_selection,
    load_preview,
    stash_preview,
)
from services.command_import.sources.nightbot import NightbotAuthError, NightbotSource
from services.command_import.sources.streamelements import ChannelNotOnStreamElementsError
from services.oauth_service import decode_oauth_state, encode_oauth_state
from shared.errors import InvalidInputError, NotFoundError

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commands/import", tags=["command-import"])

NIGHTBOT_CALLBACK_PATH = "/api/commands/import/nightbot/callback"
_OAUTH_MODE = "nightbot_import"

# Shared client so repeated previews reuse connections. Third-party APIs, so a
# tight timeout — a slow Nightbot must not hold a dashboard request open.
_http = httpx.AsyncClient(timeout=15.0)


async def close_command_import_http_client() -> None:
    """Close the shared client on shutdown (called from the app lifespan)."""
    await _http.aclose()


class ImportSourceUnavailableError(InvalidInputError):
    code = "COMMAND_IMPORT.SOURCE_UNAVAILABLE"
    user_message = "這個匯入來源目前沒有開放"


class SourceChannelNotFoundError(NotFoundError):
    code = "COMMAND_IMPORT.CHANNEL_NOT_FOUND"
    user_message = "在這個平台上找不到你的頻道"


class PreviewExpiredError(NotFoundError):
    code = "COMMAND_IMPORT.PREVIEW_EXPIRED"
    user_message = "匯入清單已經過期，請重新讀取一次"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ImportSourceInfo(BaseModel):
    source: str
    available: bool
    reason: str | None = None


class ImportPreviewResponse(BaseModel):
    import_id: str
    source: str
    source_channel: str
    # The dataclass is the wire format. Restating its 15 fields in a second
    # model only creates a place to forget one; StrEnum members serialize as
    # their string value already.
    items: list[ImportItem]
    default_selection: dict[str, bool]


class ImportApplyRequest(BaseModel):
    import_id: str
    selections: dict[str, bool]
    """Item key → whether the imported command should start enabled."""


class ImportApplyResponse(BaseModel):
    created: int
    enabled: int
    skipped: int
    failed: int
    errors: list[str]


def _service(pool=Depends(get_db_pool)) -> CommandImportService:
    return CommandImportService(pool, _http)


def _to_response(import_id: str, preview: ImportPreview) -> ImportPreviewResponse:
    return ImportPreviewResponse(
        import_id=import_id,
        source=preview.source.value,
        source_channel=preview.source_channel,
        items=preview.items,
        default_selection=default_selection(preview),
    )


async def _resolve_login(ctx: TenantContext, twitch_api: TwitchAPIClient) -> str:
    """The caller's Twitch login, which is how both platforms key a channel."""
    if ctx.channel_name:
        return ctx.channel_name
    info = await twitch_api.get_user_info(ctx.channel_id)
    if not info or not info.get("name"):
        raise SourceChannelNotFoundError(context={"channel_id": ctx.channel_id})
    return str(info["name"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/sources", response_model=list[ImportSourceInfo])
async def list_sources(
    _: None = Depends(require_activated),
    settings: Settings = Depends(get_settings),
) -> list[ImportSourceInfo]:
    """Which import sources this deployment can offer."""
    nightbot_ready = bool(settings.nightbot_client_id and settings.nightbot_client_secret)
    return [
        ImportSourceInfo(source="streamelements", available=True),
        ImportSourceInfo(
            source="nightbot",
            available=nightbot_ready,
            reason=None if nightbot_ready else "尚未設定 Nightbot 應用程式金鑰",
        ),
    ]


@router.get("/streamelements/preview", response_model=ImportPreviewResponse)
async def preview_streamelements(
    ctx: TenantContext = Depends(_require_tenant),
    service: CommandImportService = Depends(_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> ImportPreviewResponse:
    """Read the caller's StreamElements commands. No authorization needed."""
    login = await _resolve_login(ctx, twitch_api)
    try:
        preview = await service.preview_streamelements(ctx.channel_id, login)
    except ChannelNotOnStreamElementsError as exc:
        raise SourceChannelNotFoundError(
            user_message="在 StreamElements 上找不到你的頻道",
            context={"login": login},
        ) from exc
    import_id = stash_preview(ctx.user_id, preview)
    LOGGER.info("command_import_preview", extra={"source": "streamelements", "login": login})
    return _to_response(import_id, preview)


@router.get("/nightbot/oauth")
async def start_nightbot_oauth(
    ctx: TenantContext = Depends(_require_tenant),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Return the Nightbot consent URL.

    Nightbot's unauthenticated read redacts every variable, so a faithful
    import has to go through OAuth.
    """
    if not (settings.nightbot_client_id and settings.nightbot_client_secret):
        raise ImportSourceUnavailableError(context={"source": "nightbot"})
    source = NightbotSource(_http, settings.nightbot_client_id, settings.nightbot_client_secret)
    state = encode_oauth_state(_OAUTH_MODE, ctx.user_id, secret=settings.jwt_secret_key)
    return {"oauth_url": source.authorize_url(f"{settings.api_url}{NIGHTBOT_CALLBACK_PATH}", state)}


@router.get("/nightbot/callback")
async def nightbot_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    settings: Settings = Depends(get_settings),
    pool=Depends(get_db_pool),
) -> RedirectResponse:
    """Exchange the code, build the preview, and drop the token immediately.

    The access token is never persisted: it is used inside this one request and
    revoked before the redirect, matching the collaborator OAuth flow in
    auth_router which also proves something without keeping the credential.
    """
    # The dashboard Commands page is /commands, not /dashboard/commands — the
    # latter is caught by the public "/:username/commands" route and renders a
    # channel lookup for a user literally named "dashboard".
    landing = f"{settings.frontend_url}/commands"
    if error:
        return RedirectResponse(url=f"{landing}?import_error={_url_quote(error, safe='')}")

    decoded = decode_oauth_state(state, secret=settings.jwt_secret_key)
    if decoded.get("mode") != _OAUTH_MODE or not decoded.get("uid"):
        LOGGER.warning("Nightbot import callback received invalid state — rejecting")
        return RedirectResponse(url=f"{landing}?import_error=invalid_state")
    if not code:
        return RedirectResponse(url=f"{landing}?import_error=no_code")

    user_id = str(decoded["uid"])
    service = CommandImportService(pool, _http)
    source = NightbotSource(_http, settings.nightbot_client_id, settings.nightbot_client_secret)

    try:
        token = await source.exchange_code(code, f"{settings.api_url}{NIGHTBOT_CALLBACK_PATH}")
    except NightbotAuthError as exc:
        LOGGER.warning("Nightbot token exchange failed: %s", exc)
        return RedirectResponse(url=f"{landing}?import_error=token_exchange_failed")

    channel_id = await _channel_id_for_user(pool, user_id)
    if not channel_id:
        await source.revoke(token)
        return RedirectResponse(url=f"{landing}?import_error=channel_not_found")

    try:
        preview = await service.preview_nightbot(channel_id, token)
    except Exception:
        LOGGER.exception("Nightbot import preview failed")
        return RedirectResponse(url=f"{landing}?import_error=fetch_failed")

    import_id = stash_preview(user_id, preview)
    LOGGER.info("command_import_preview", extra={"source": "nightbot"})
    return RedirectResponse(url=f"{landing}?import=nightbot&import_id={import_id}")


@router.get("/preview/{import_id}", response_model=ImportPreviewResponse)
async def get_preview(
    import_id: str,
    ctx: TenantContext = Depends(_require_tenant),
    service: CommandImportService = Depends(_service),
) -> ImportPreviewResponse:
    """Fetch a preview stashed by the OAuth round trip."""
    try:
        preview = load_preview(ctx.user_id, import_id)
    except PreviewNotFoundError as exc:
        raise PreviewExpiredError(context={"import_id": import_id}) from exc
    return _to_response(import_id, preview)


@router.post("/apply", response_model=ImportApplyResponse)
async def apply_import(
    body: ImportApplyRequest,
    ctx: TenantContext = Depends(_require_tenant),
    service: CommandImportService = Depends(_service),
) -> ImportApplyResponse:
    """Write the selected commands. Conflicts are re-checked against the DB."""
    try:
        preview = load_preview(ctx.user_id, body.import_id)
    except PreviewNotFoundError as exc:
        raise PreviewExpiredError(context={"import_id": body.import_id}) from exc

    result = await service.apply(ctx.channel_id, preview, body.selections)
    # "created" is a reserved LogRecord attribute — logging raises KeyError on
    # it, which turned a successful import into a 500 after the rows were
    # already written.
    LOGGER.info(
        "command_import_applied",
        extra={
            "source": preview.source.value,
            "imported": result.created,
            "skipped": result.skipped,
            "failed": result.failed,
        },
    )
    return ImportApplyResponse(**asdict(result))


async def _channel_id_for_user(pool, user_id: str) -> str | None:
    """Look up the caller's platform_user_id — the OAuth callback has no JWT.

    Returns None on any failure so the callback redirects with a readable
    message instead of surfacing a 500 in the middle of the OAuth round trip.
    """
    try:
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT platform_user_id FROM identities "
                "WHERE user_id = $1::uuid AND platform = 'twitch' LIMIT 1",
                user_id,
            )
    except Exception:
        LOGGER.exception("Nightbot import could not resolve the caller's channel")
        return None
