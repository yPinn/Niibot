"""Characterization tests for services.twitch_api.TwitchAPIClient.

This client has no other direct coverage (router tests mock get_twitch_api
wholesale), so these tests pin down its current observable behaviour before
the module is split into a mixin sub-package. They drive the real request
pipeline via httpx.MockTransport — params, headers, JSON decoding, and
status-code branching are all exercised for real.
"""

from __future__ import annotations

import httpx
import pytest

from services.twitch_api import OAUTH_BASE, TokenRefreshResult, TwitchAPIClient


class _MockAPI:
    """Records requests and replies from a per-key queue of responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._queues: dict[tuple[str, str], list[httpx.Response]] = {}

    def route(self, method: str, url_fragment: str, *responses: httpx.Response) -> _MockAPI:
        self._queues[(method, url_fragment)] = list(responses)
        return self

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for (method, fragment), queue in self._queues.items():
            if request.method == method and fragment in str(request.url):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(404, json={"error": f"unrouted {request.method} {request.url}"})

    def client(self) -> TwitchAPIClient:
        api = TwitchAPIClient("test-client-id", "test-client-secret", "https://api.example.com")
        api._http = httpx.AsyncClient(transport=httpx.MockTransport(self._handler))
        return api

    def paths(self, method: str | None = None) -> list[str]:
        return [r.url.path for r in self.requests if method is None or r.method == method]


def _app_token(expires_in: int = 3600, token: str = "app-tok") -> httpx.Response:
    return httpx.Response(200, json={"access_token": token, "expires_in": expires_in})


# ---------------------------------------------------------------------------
# parse_duration
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_full_string(self):
        assert TwitchAPIClient.parse_duration("3h2m1s") == pytest.approx(3 + 2 / 60 + 1 / 3600)

    def test_hours_only(self):
        assert TwitchAPIClient.parse_duration("2h") == 2.0

    def test_minutes_only(self):
        assert TwitchAPIClient.parse_duration("30m") == 0.5

    def test_empty_string_is_zero(self):
        assert TwitchAPIClient.parse_duration("") == 0.0


# ---------------------------------------------------------------------------
# generate_oauth_url
# ---------------------------------------------------------------------------


class TestGenerateOAuthUrl:
    def test_contains_core_params(self):
        api = _MockAPI().client()
        url = api.generate_oauth_url()
        assert url.startswith(f"{OAUTH_BASE}/authorize")
        assert "client_id=test-client-id" in url
        assert "response_type=code" in url
        assert "force_verify=true" in url
        # redirect_uri is percent-encoded
        assert "redirect_uri=https%3A%2F%2Fapi.example.com%2Fapi%2Fauth%2Ftwitch%2Fcallback" in url
        # scopes use %3A for the colon
        assert "%3A" in url

    def test_state_appended_when_given(self):
        api = _MockAPI().client()
        assert "&state=abc123" in api.generate_oauth_url("abc123")

    def test_state_absent_when_omitted(self):
        api = _MockAPI().client()
        assert "state=" not in api.generate_oauth_url()


# ---------------------------------------------------------------------------
# _ensure_app_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEnsureAppToken:
    async def test_fetches_and_returns_token(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token(token="fresh"))
        api = mock.client()

        assert await api._ensure_app_token() == "fresh"
        req = mock.requests[0]
        assert b"grant_type=client_credentials" in req.content

    async def test_second_call_uses_cache(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token(expires_in=3600))
        api = mock.client()

        await api._ensure_app_token()
        await api._ensure_app_token()

        assert len(mock.paths("POST")) == 1

    async def test_refetches_when_expired(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/token", _app_token(expires_in=0), _app_token(expires_in=0)
        )
        api = mock.client()

        await api._ensure_app_token()
        await api._ensure_app_token()

        assert len(mock.paths("POST")) == 2

    async def test_non_200_returns_none(self):
        mock = _MockAPI().route("POST", "/oauth2/token", httpx.Response(500, json={}))
        api = mock.client()

        assert await api._ensure_app_token() is None


# ---------------------------------------------------------------------------
# _helix_get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHelixGet:
    async def test_uses_app_token_and_sets_headers(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token(token="app-x"))
        mock.route("GET", "/helix/users", httpx.Response(200, json={"data": []}))
        api = mock.client()

        resp = await api._helix_get("users", {"login": "foo"})

        assert resp is not None and resp.status_code == 200
        get_req = next(r for r in mock.requests if r.method == "GET")
        assert get_req.headers["Authorization"] == "Bearer app-x"
        assert get_req.headers["Client-Id"] == "test-client-id"
        assert get_req.url.params["login"] == "foo"

    async def test_returns_none_when_app_token_unavailable(self):
        mock = _MockAPI().route("POST", "/oauth2/token", httpx.Response(401, json={}))
        api = mock.client()

        assert await api._helix_get("users") is None
        assert mock.paths("GET") == []

    async def test_passes_explicit_token_without_fetching_app_token(self):
        mock = _MockAPI().route("GET", "/helix/users", httpx.Response(200, json={"data": []}))
        api = mock.client()

        await api._helix_get("users", token="user-tok")

        assert mock.paths("POST") == []
        assert mock.requests[0].headers["Authorization"] == "Bearer user-tok"

    async def test_non_200_response_is_returned_as_is(self):
        mock = _MockAPI().route("GET", "/helix/users", httpx.Response(403, json={"message": "no"}))
        api = mock.client()

        resp = await api._helix_get("users", token="t")
        assert resp is not None and resp.status_code == 403


# ---------------------------------------------------------------------------
# exchange_code_for_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExchangeCodeForToken:
    async def test_success_returns_token_data(self):
        mock = _MockAPI().route(
            "POST",
            "/oauth2/token",
            httpx.Response(
                200,
                json={
                    "access_token": "user-at",
                    "refresh_token": "user-rt",
                    "scope": ["channel:bot", "channel:read:redemptions"],
                },
            ),
        )
        mock.route("GET", "/helix/users", httpx.Response(200, json={"data": [{"id": "12345"}]}))
        api = mock.client()

        ok, err, data = await api.exchange_code_for_token("the-code")

        assert ok is True
        assert err is None
        assert data == {
            "access_token": "user-at",
            "refresh_token": "user-rt",
            "user_id": "12345",
            "scopes": "channel:bot channel:read:redemptions",
        }

    async def test_token_endpoint_non_200(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/token", httpx.Response(400, json={"message": "bad code"})
        )
        api = mock.client()

        ok, err, data = await api.exchange_code_for_token("x")
        assert (ok, err, data) == (False, "token_exchange_failed", None)

    async def test_missing_access_token(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/token", httpx.Response(200, json={"refresh_token": "r"})
        )
        api = mock.client()

        ok, err, data = await api.exchange_code_for_token("x")
        assert (ok, err, data) == (False, "no_access_token", None)

    async def test_user_fetch_failure(self):
        mock = _MockAPI().route(
            "POST",
            "/oauth2/token",
            httpx.Response(200, json={"access_token": "at", "refresh_token": "rt"}),
        )
        mock.route("GET", "/helix/users", httpx.Response(200, json={"data": []}))
        api = mock.client()

        ok, err, data = await api.exchange_code_for_token("x")
        assert (ok, err, data) == (False, "user_fetch_failed", None)


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRefreshAccessToken:
    async def test_success_with_rotated_refresh_token(self):
        mock = _MockAPI().route(
            "POST",
            "/oauth2/token",
            httpx.Response(200, json={"access_token": "new-at", "refresh_token": "new-rt"}),
        )
        api = mock.client()

        result = await api.refresh_access_token("old-rt")

        assert isinstance(result, TokenRefreshResult)
        assert result.success is True
        assert result.access_token == "new-at"
        assert result.refresh_token == "new-rt"

    async def test_success_keeps_old_refresh_token_when_not_rotated(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/token", httpx.Response(200, json={"access_token": "new-at"})
        )
        api = mock.client()

        result = await api.refresh_access_token("old-rt")
        assert result.success is True
        assert result.refresh_token == "old-rt"

    async def test_non_200_returns_failure_with_message(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/token", httpx.Response(400, json={"message": "invalid grant"})
        )
        api = mock.client()

        result = await api.refresh_access_token("rt")
        assert result.success is False
        assert result.error == "invalid grant"

    async def test_200_without_access_token_is_failure(self):
        mock = _MockAPI().route("POST", "/oauth2/token", httpx.Response(200, json={}))
        api = mock.client()

        result = await api.refresh_access_token("rt")
        assert result.success is False


# ---------------------------------------------------------------------------
# _fetch_paginated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchPaginated:
    async def test_follows_cursor_across_pages(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/moderation/moderators",
            httpx.Response(
                200,
                json={"data": [{"user_id": "1"}], "pagination": {"cursor": "CUR2"}},
            ),
            httpx.Response(200, json={"data": [{"user_id": "2"}], "pagination": {}}),
        )
        api = mock.client()

        results = await api._fetch_paginated(
            "moderation/moderators", {"broadcaster_id": "b1"}, token="t"
        )

        assert [r["user_id"] for r in results] == ["1", "2"]
        first, second = [r for r in mock.requests if r.method == "GET"]
        assert first.url.params["first"] == "100"
        assert "after" not in first.url.params
        assert second.url.params["after"] == "CUR2"

    async def test_stops_on_non_200_keeping_prior_results(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/subscriptions",
            httpx.Response(200, json={"data": [{"user_id": "1"}], "pagination": {"cursor": "C"}}),
            httpx.Response(401, json={"message": "scope missing"}),
        )
        api = mock.client()

        results = await api._fetch_paginated("subscriptions", {"broadcaster_id": "b"}, token="t")
        assert [r["user_id"] for r in results] == ["1"]

    async def test_single_page_no_cursor(self):
        mock = _MockAPI().route(
            "GET", "/helix/channels/vips", httpx.Response(200, json={"data": [], "pagination": {}})
        )
        api = mock.client()

        assert await api._fetch_paginated("channels/vips", {"broadcaster_id": "b"}, token="t") == []


# ---------------------------------------------------------------------------
# get_bot_mod_status — the four documented branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetBotModStatus:
    async def test_mod(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/moderation/moderators",
            httpx.Response(200, json={"data": [{"user_id": "bot"}]}),
        )
        api = mock.client()
        assert await api.get_bot_mod_status("b", "bot", "tok") == "mod"

    async def test_no_mod(self):
        mock = _MockAPI().route(
            "GET", "/helix/moderation/moderators", httpx.Response(200, json={"data": []})
        )
        api = mock.client()
        assert await api.get_bot_mod_status("b", "bot", "tok") == "no_mod"

    async def test_scope_error_on_401(self):
        mock = _MockAPI().route(
            "GET", "/helix/moderation/moderators", httpx.Response(401, json={"message": "scope"})
        )
        api = mock.client()
        assert await api.get_bot_mod_status("b", "bot", "tok") == "scope_error"

    async def test_token_error_on_other_non_200(self):
        mock = _MockAPI().route("GET", "/helix/moderation/moderators", httpx.Response(500, json={}))
        api = mock.client()
        assert await api.get_bot_mod_status("b", "bot", "tok") == "token_error"


# ---------------------------------------------------------------------------
# user + follower helpers (representative mapping behaviour)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserHelpers:
    async def test_get_user_by_login_maps_fields(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token())
        mock.route(
            "GET",
            "/helix/users",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "42",
                            "login": "foo",
                            "display_name": "Foo",
                            "profile_image_url": "http://img/x.png",
                            "offline_image_url": "",
                            "broadcaster_type": "partner",
                            "created_at": "2020-01-01T00:00:00Z",
                        }
                    ]
                },
            ),
        )
        api = mock.client()

        user = await api.get_user_by_login("foo")
        assert user == {
            "id": "42",
            "name": "foo",
            "display_name": "Foo",
            "avatar": "http://img/x.png",
            "offline_image_url": None,
            "broadcaster_type": "partner",
            "account_created_at": "2020-01-01T00:00:00Z",
        }
        assert mock.requests[-1].url.params["login"] == "foo"

    async def test_get_user_by_login_returns_none_when_absent(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token())
        mock.route("GET", "/helix/users", httpx.Response(200, json={"data": []}))
        api = mock.client()
        assert await api.get_user_by_login("ghost") is None

    async def test_fetch_all_followers_filters_and_maps(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/channels/followers",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "user_id": "1",
                            "user_login": "a",
                            "user_name": "A",
                            "followed_at": "2021-01-01T00:00:00Z",
                        },
                        {"user_login": "b", "followed_at": "2021-01-02T00:00:00Z"},
                        {"user_id": "3", "user_login": "c"},
                    ],
                    "pagination": {},
                },
            ),
        )
        api = mock.client()

        followers = await api.fetch_all_followers("b1", "tok")
        assert followers == [
            {
                "user_id": "1",
                "user_login": "a",
                "user_name": "A",
                "followed_at": "2021-01-01T00:00:00Z",
            }
        ]


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_closes_http_client():
    api = _MockAPI().client()
    await api.close()
    assert api._http.is_closed
