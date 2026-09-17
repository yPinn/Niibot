"""Tests for api.routers.command_import_router and the apply path.

External HTTP is stubbed with recorded response shapes — the suite never calls
Nightbot or StreamElements.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-command-import-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("API_URL", "https://api.niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_db_pool,
    get_twitch_api,
    require_activated,
    require_self_tenant_access,
)
from core.error_handlers import register_exception_handlers
from routers.command_import_router import router as _import_router
from services import TenantContext
from services.command_import.models import (
    ImportItem,
    ImportPreview,
    ImportSection,
    ImportSource,
    ImportStatus,
)
from services.command_import.service import (
    CommandImportService,
    default_selection,
    stash_preview,
)
from services.oauth_service import encode_oauth_state

CHANNEL_ID = "ch-123"
USER_UUID = "11111111-2222-3333-4444-555555555555"
LOGIN = "niistream"

# ── Recorded StreamElements shapes ──────────────────────────────────────────

SE_CHANNEL = {"_id": "se-channel-1", "username": LOGIN, "providerId": CHANNEL_ID}
SE_CUSTOM = [
    {
        "command": "discord",
        "reply": "加入我們 https://discord.gg/example",
        "aliases": ["dc"],
        "keywords": [],
        "enabled": True,
        "cost": 0,
        "type": "say",
        "accessLevel": 100,
        "cooldown": {"user": 15, "global": 15},
    },
    {
        "command": "hug",
        "reply": "$(1|$(sender)) 抱了一下",
        "aliases": [],
        "keywords": ["抱抱"],
        "enabled": False,
        "cost": 0,
        "type": "say",
        "accessLevel": 100,
        "cooldown": {"user": 30, "global": 5},
    },
    {
        "command": "pb",
        "reply": "$(customapi https://example.com/pb)",
        "aliases": [],
        "keywords": [],
        "enabled": True,
        "cost": 0,
        "type": "say",
        "accessLevel": 100,
        "cooldown": {"user": 15, "global": 15},
    },
]
SE_DEFAULT = [
    {"command": "followage", "enabled": True},
    {"command": "songrequest", "enabled": True},
    {"command": "points", "enabled": False},
]


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(*, twitch_api: MagicMock | None = None) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_import_router)
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID,
        user_id=USER_UUID,
        role="owner",
        channel_name=LOGIN,
    )
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: twitch_api or MagicMock()
    return TestClient(app, raise_server_exceptions=False)


def _se_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(f"/channels/{LOGIN}"):
            return httpx.Response(200, json=SE_CHANNEL)
        if path.endswith("/default"):
            return httpx.Response(200, json=SE_DEFAULT)
        if "/bot/commands/" in path:
            return httpx.Response(200, json=SE_CUSTOM)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


@asynccontextmanager
async def _stubbed(transport: httpx.MockTransport | None = None, existing: set[str] | None = None):
    """Swap the router's shared HTTP client and the channel's existing names."""
    import routers.command_import_router as mod

    original = mod._http
    mod._http = httpx.AsyncClient(transport=transport or _se_transport())
    patcher = patch.object(
        CommandImportService, "existing_names", AsyncMock(return_value=existing or set())
    )
    patcher.start()
    try:
        yield
    finally:
        patcher.stop()
        await mod._http.aclose()
        mod._http = original


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------


class TestSources:
    def test_streamelements_always_available(self):
        r = _make_client().get("/api/commands/import/sources")
        assert r.status_code == 200
        se = next(s for s in r.json() if s["source"] == "streamelements")
        assert se["available"] is True

    def test_nightbot_hidden_without_credentials(self):
        r = _make_client().get("/api/commands/import/sources")
        nb = next(s for s in r.json() if s["source"] == "nightbot")
        assert nb["available"] is False
        assert nb["reason"]

    def test_nightbot_available_when_configured(self, monkeypatch):
        monkeypatch.setenv("NIGHTBOT_CLIENT_ID", "id")
        monkeypatch.setenv("NIGHTBOT_CLIENT_SECRET", "secret")
        get_settings.cache_clear()
        r = _make_client().get("/api/commands/import/sources")
        nb = next(s for s in r.json() if s["source"] == "nightbot")
        assert nb["available"] is True
        assert nb["reason"] is None


# ---------------------------------------------------------------------------
# GET /streamelements/preview
# ---------------------------------------------------------------------------


class TestStreamElementsPreview:
    @pytest.mark.asyncio
    async def test_preview_sorts_items_into_sections(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "streamelements"
        assert body["source_channel"] == LOGIN

        by_name = {i["source_name"]: i for i in body["items"]}
        assert by_name["!discord"]["section"] == "custom"
        assert by_name["!hug"]["section"] == "custom"
        assert by_name["!pb"]["section"] == "unsupported"
        # The default followage maps onto our builtin; songrequest has no
        # equivalent and is listed rather than silently dropped.
        assert by_name["!followage"]["section"] == "builtin"
        assert by_name["!followage"]["builtin_target"] == "followage"
        assert by_name["!songrequest"]["section"] == "unsupported"

    @pytest.mark.asyncio
    async def test_disabled_default_commands_are_not_listed(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        assert all(i["source_name"] != "!points" for i in r.json()["items"])

    @pytest.mark.asyncio
    async def test_keyword_becomes_a_trigger_row(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        triggers = [i for i in r.json()["items"] if i["section"] == "trigger"]
        assert len(triggers) == 1
        assert triggers[0]["pattern"] == "抱抱"

    @pytest.mark.asyncio
    async def test_variables_are_translated_and_the_original_kept(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        hug = next(i for i in r.json()["items"] if i["source_name"] == "!hug")
        assert hug["response"] == "$(touser) 抱了一下"
        assert hug["original_response"] == "$(1|$(sender)) 抱了一下"

    @pytest.mark.asyncio
    async def test_source_enabled_state_is_reported(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        by_name = {i["source_name"]: i for i in r.json()["items"]}
        assert by_name["!discord"]["source_enabled"] is True
        assert by_name["!hug"]["source_enabled"] is False

    @pytest.mark.asyncio
    async def test_unsupported_rows_are_not_preselected(self):
        async with _stubbed():
            r = _make_client().get("/api/commands/import/streamelements/preview")
        body = r.json()
        selected = body["default_selection"]
        unsupported = [i["key"] for i in body["items"] if i["section"] == "unsupported"]
        assert unsupported
        assert all(key not in selected for key in unsupported)
        # Everything preselected defaults to OFF, not enabled.
        assert all(value is False for value in selected.values())

    @pytest.mark.asyncio
    async def test_unknown_channel_returns_404(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(404, json={}))
        async with _stubbed(transport):
            r = _make_client().get("/api/commands/import/streamelements/preview")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_login_falls_back_to_twitch_lookup(self):
        app_client = TestClient(
            _app_without_channel_name(twitch_api=_twitch_api_returning(LOGIN)),
            raise_server_exceptions=False,
        )
        async with _stubbed():
            r = app_client.get("/api/commands/import/streamelements/preview")
        assert r.status_code == 200
        assert r.json()["source_channel"] == LOGIN


def _twitch_api_returning(login: str) -> MagicMock:
    api = MagicMock()
    api.get_user_info = AsyncMock(return_value={"id": CHANNEL_ID, "name": login})
    return api


def _app_without_channel_name(*, twitch_api: MagicMock) -> FastAPI:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_import_router)
    app.dependency_overrides[require_activated] = lambda: None
    app.dependency_overrides[require_self_tenant_access] = lambda: TenantContext(
        channel_id=CHANNEL_ID, user_id=USER_UUID, role="owner"
    )
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[get_twitch_api] = lambda: twitch_api
    return app


# ---------------------------------------------------------------------------
# Nightbot OAuth
# ---------------------------------------------------------------------------


class TestNightbotOAuth:
    def test_start_requires_configured_credentials(self):
        r = _make_client().get("/api/commands/import/nightbot/oauth")
        assert r.status_code == 400

    def test_start_returns_a_consent_url(self, monkeypatch):
        monkeypatch.setenv("NIGHTBOT_CLIENT_ID", "cid")
        monkeypatch.setenv("NIGHTBOT_CLIENT_SECRET", "secret")
        get_settings.cache_clear()
        r = _make_client().get("/api/commands/import/nightbot/oauth")
        assert r.status_code == 200
        url = r.json()["oauth_url"]
        assert url.startswith("https://api.nightbot.tv/oauth2/authorize?")
        assert "client_id=cid" in url
        assert "scope=commands+commands_default" in url
        assert "state=" in url
        assert "client_secret" not in url

    def test_callback_rejects_a_forged_state(self):
        client = _make_client()
        r = client.get(
            "/api/commands/import/nightbot/callback",
            params={"code": "abc", "state": "not-a-signed-state"},
            follow_redirects=False,
        )
        assert r.status_code == 307
        assert "import_error=invalid_state" in r.headers["location"]

    def test_callback_rejects_a_state_for_another_flow(self):
        settings = get_settings()
        state = encode_oauth_state("login", USER_UUID, secret=settings.jwt_secret_key)
        r = _make_client().get(
            "/api/commands/import/nightbot/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert "import_error=invalid_state" in r.headers["location"]

    def test_callback_surfaces_a_denied_consent(self):
        r = _make_client().get(
            "/api/commands/import/nightbot/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert "import_error=access_denied" in r.headers["location"]

    def test_callback_lands_on_the_dashboard_commands_route(self):
        # The dashboard page is /commands. "/dashboard/commands" matches the
        # public "/:username/commands" route instead and renders a channel
        # lookup for a user named "dashboard".
        r = _make_client().get(
            "/api/commands/import/nightbot/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert r.headers["location"].startswith("https://niibot.tv/commands?")

    def test_callback_without_a_code_is_rejected(self):
        settings = get_settings()
        state = encode_oauth_state("nightbot_import", USER_UUID, secret=settings.jwt_secret_key)
        r = _make_client().get(
            "/api/commands/import/nightbot/callback",
            params={"state": state},
            follow_redirects=False,
        )
        assert "import_error=no_code" in r.headers["location"]


# ---------------------------------------------------------------------------
# Preview cache
# ---------------------------------------------------------------------------


def _preview() -> ImportPreview:
    return ImportPreview(
        source=ImportSource.STREAMELEMENTS,
        source_channel=LOGIN,
        items=[
            ImportItem(
                key="se:cmd:discord",
                section=ImportSection.CUSTOM,
                status=ImportStatus.OK,
                source_name="!discord",
                source_enabled=True,
                command_name="discord",
                response="加入我們",
            )
        ],
    )


class TestPreviewCache:
    def test_preview_is_retrievable_by_its_owner(self):
        import_id = stash_preview(USER_UUID, _preview())
        r = _make_client().get(f"/api/commands/import/preview/{import_id}")
        assert r.status_code == 200
        assert r.json()["items"][0]["command_name"] == "discord"

    def test_another_user_cannot_read_it(self):
        import_id = stash_preview("someone-else", _preview())
        r = _make_client().get(f"/api/commands/import/preview/{import_id}")
        assert r.status_code == 404

    def test_unknown_id_returns_404(self):
        r = _make_client().get("/api/commands/import/preview/does-not-exist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _items() -> list[ImportItem]:
    return [
        ImportItem(
            key="cmd:discord",
            section=ImportSection.CUSTOM,
            status=ImportStatus.OK,
            source_name="!discord",
            source_enabled=True,
            command_name="discord",
            response="加入我們",
            cooldown=15,
            min_role="everyone",
            aliases=["dc"],
        ),
        ImportItem(
            key="cmd:taken",
            section=ImportSection.CUSTOM,
            status=ImportStatus.CONFLICT,
            source_name="!taken",
            source_enabled=True,
            command_name="taken",
            response="whatever",
        ),
        ImportItem(
            key="trigger:hug",
            section=ImportSection.TRIGGER,
            status=ImportStatus.OK,
            source_name="抱抱",
            source_enabled=True,
            command_name="hug",
            response="$(touser) 抱了一下",
            pattern="抱抱",
            aliases=["hugs"],
        ),
        ImportItem(
            key="builtin:followage",
            section=ImportSection.BUILTIN,
            status=ImportStatus.OK,
            source_name="!followage",
            source_enabled=True,
            builtin_target="followage",
        ),
        ImportItem(
            key="nope:pb",
            section=ImportSection.UNSUPPORTED,
            status=ImportStatus.UNSUPPORTED,
            source_name="!pb",
            source_enabled=True,
        ),
    ]


def _service_with(
    existing: set[str] | None = None, triggers: set[str] | None = None
) -> CommandImportService:
    """A service whose writes go to mocks but keep the repositories' contract:
    the insert-only primitives return None when the name is already taken.
    """
    service = CommandImportService(AsyncMock(), MagicMock())
    service.existing_names = AsyncMock(return_value=existing or set())
    service.existing_trigger_names = AsyncMock(return_value=triggers or set())
    service.commands = MagicMock()
    service.commands.toggle_command = AsyncMock()
    service.cmd_repo = MagicMock()
    service.cmd_repo.try_insert_config = AsyncMock(return_value=MagicMock())
    service.trigger_repo = MagicMock()
    service.trigger_repo.try_insert = AsyncMock(return_value=MagicMock())
    service.trigger_repo.upsert = AsyncMock()
    return service


class TestApply:
    @pytest.mark.asyncio
    async def test_creates_selected_command_disabled_by_default(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"cmd:discord": False})

        assert result.created == 1
        assert result.enabled == 0
        kwargs = service.cmd_repo.try_insert_config.await_args.kwargs
        assert kwargs["enabled"] is False
        assert kwargs["custom_response"] == "加入我們"
        assert kwargs["aliases"] == "dc"

    @pytest.mark.asyncio
    async def test_respects_a_per_item_enable(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"cmd:discord": True})

        assert result.enabled == 1
        assert service.cmd_repo.try_insert_config.await_args.kwargs["enabled"] is True

    @pytest.mark.asyncio
    async def test_conflicts_are_skipped_even_if_selected(self):
        service = _service_with({"taken"})
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"cmd:taken": True})

        assert result.created == 0
        assert result.skipped == 1
        service.cmd_repo.try_insert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_conflicting_alias_is_dropped_but_command_still_imports(self):
        service = _service_with({"dc"})
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"cmd:discord": False})

        assert result.created == 1
        assert service.cmd_repo.try_insert_config.await_args.kwargs["aliases"] is None

    @pytest.mark.asyncio
    async def test_unsupported_rows_are_never_written(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"nope:pb": True})

        assert result.created == 0
        assert result.skipped == 1
        service.cmd_repo.try_insert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_builtin_row_toggles_instead_of_creating(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"builtin:followage": True})

        assert result.created == 1
        service.commands.toggle_command.assert_awaited_once_with(CHANNEL_ID, "followage", True)
        service.cmd_repo.try_insert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trigger_row_creates_a_trigger(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"trigger:hug": False})

        assert result.created == 1
        kwargs = service.trigger_repo.try_insert.await_args.kwargs
        assert kwargs["pattern"] == "抱抱"
        assert kwargs["match_type"] == "contains"
        assert kwargs["enabled"] is False
        assert kwargs["aliases"] == "hugs"

    @pytest.mark.asyncio
    async def test_existing_trigger_name_is_never_overwritten(self):
        service = _service_with(triggers={"hug"})
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"trigger:hug": True})

        assert result.created == 0
        assert result.skipped == 1
        service.trigger_repo.try_insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trigger_lost_to_a_concurrent_writer_is_skipped(self):
        # try_insert returns None when the unique constraint rejects the row —
        # a name that appeared after the preview was built must not be clobbered.
        service = _service_with()
        service.trigger_repo.try_insert = AsyncMock(return_value=None)
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"trigger:hug": True})

        assert result.created == 0
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_command_lost_to_a_concurrent_writer_is_skipped(self):
        service = _service_with()
        service.cmd_repo.try_insert_config = AsyncMock(return_value=None)
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"cmd:discord": True})

        assert result.created == 0
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_a_failing_row_does_not_abort_the_batch(self):
        service = _service_with(set())
        service.cmd_repo.try_insert_config = AsyncMock(side_effect=RuntimeError("boom"))
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(
            CHANNEL_ID, preview, {"cmd:discord": False, "builtin:followage": False}
        )

        assert result.failed == 1
        assert result.created == 1  # the builtin toggle still went through
        assert result.errors

    @pytest.mark.asyncio
    async def test_rerunning_the_same_import_is_a_no_op(self):
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())
        selection = default_selection(preview)

        first = _service_with(set())
        await first.apply(CHANNEL_ID, preview, selection)

        # Second run sees the names the first one created.
        second = _service_with({"discord", "dc", "hug"})
        second.trigger_repo.try_insert = AsyncMock(side_effect=AssertionError("must not rerun"))
        result = await second.apply(CHANNEL_ID, preview, {"cmd:discord": False})

        assert result.created == 0
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_unknown_key_is_skipped(self):
        service = _service_with(set())
        preview = ImportPreview(ImportSource.STREAMELEMENTS, LOGIN, _items())

        result = await service.apply(CHANNEL_ID, preview, {"does-not-exist": True})

        assert result.skipped == 1
        assert result.created == 0


# ---------------------------------------------------------------------------
# The two DB reads apply() does before its per-item guard
# ---------------------------------------------------------------------------


def _pool_returning(rows: list[dict]) -> MagicMock:
    """A pool whose conn.fetch returns *rows*, shaped like asyncpg's."""
    conn = AsyncMock()
    conn.fetch.return_value = rows
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


_TRIGGER_ROW = {
    "id": 1,
    "channel_id": CHANNEL_ID,
    "trigger_name": "Hello",
    "match_type": "contains",
    "pattern": "hello",
    "case_sensitive": False,
    "response": "hi",
    "min_role": "everyone",
    "cooldown": 30,
    "priority": 0,
    "enabled": True,
    "usage_count": 0,
    "aliases": None,
    "created_at": None,
    "updated_at": None,
}


class TestExistingNameLookups:
    """These run before apply()'s per-item try/except, so a failure here is a
    500 rather than a counted failure. Every other apply test mocks them out.
    """

    @pytest.mark.asyncio
    async def test_existing_trigger_names_reads_the_repository(self):
        service = CommandImportService(_pool_returning([_TRIGGER_ROW]), MagicMock())
        assert await service.existing_trigger_names(CHANNEL_ID) == {"hello"}

    @pytest.mark.asyncio
    async def test_existing_trigger_names_on_a_channel_with_none(self):
        service = CommandImportService(_pool_returning([]), MagicMock())
        assert await service.existing_trigger_names(CHANNEL_ID) == set()
