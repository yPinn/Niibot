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

from services.twitch_api import (
    OAUTH_BASE,
    TokenRefreshResult,
    TokenRevocationResult,
    TokenValidationResult,
    TwitchAPIClient,
    TwitchUsersLookupError,
)


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


@pytest.mark.asyncio
class TestGetCustomRewards:
    async def test_maps_read_only_reward_limits_and_queue_state(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/channel_points/custom_rewards",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "reward-checkin",
                            "title": "每日簽到",
                            "cost": 10,
                            "is_enabled": True,
                            "is_paused": False,
                            "is_in_stock": True,
                            "should_redemptions_skip_request_queue": True,
                            "max_per_stream_setting": {"is_enabled": True, "max_per_stream": 100},
                            "max_per_user_per_stream_setting": {
                                "is_enabled": True,
                                "max_per_user_per_stream": 1,
                            },
                        }
                    ]
                },
            ),
        )
        api = mock.client()

        rewards = await api.get_custom_rewards("channel-1", "broadcaster-token")

        assert rewards == [
            {
                "id": "reward-checkin",
                "title": "每日簽到",
                "cost": 10,
                "is_enabled": True,
                "is_paused": False,
                "is_in_stock": True,
                "should_redemptions_skip_request_queue": True,
                "max_per_stream": 100,
                "max_per_user_per_stream": 1,
            }
        ]
        assert mock.requests[-1].headers["authorization"] == "Bearer broadcaster-token"

    async def test_disabled_limits_are_returned_as_none(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/channel_points/custom_rewards",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "reward-1",
                            "title": "Reward",
                            "cost": 1,
                            "max_per_stream_setting": {"is_enabled": False, "max_per_stream": 0},
                            "max_per_user_per_stream_setting": {
                                "is_enabled": False,
                                "max_per_user_per_stream": 0,
                            },
                        }
                    ]
                },
            ),
        )

        reward = (await mock.client().get_custom_rewards("channel-1", "token"))[0]

        assert reward["max_per_stream"] is None
        assert reward["max_per_user_per_stream"] is None


@pytest.mark.asyncio
class TestGetVips:
    async def test_requires_every_page_before_returning_snapshot(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/channels/vips",
            httpx.Response(
                200,
                json={
                    "data": [{"user_id": "u1", "user_login": "alice"}],
                    "pagination": {"cursor": "next-page"},
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [{"user_id": "u2", "user_login": "bob"}],
                    "pagination": {},
                },
            ),
        )

        result = await mock.client().get_vips("channel-1", "token")

        assert [row["user_id"] for row in result] == ["u1", "u2"]
        assert mock.requests[1].url.params["after"] == "next-page"

    async def test_partial_snapshot_raises_instead_of_returning_first_page(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/channels/vips",
            httpx.Response(
                200,
                json={
                    "data": [{"user_id": "u1", "user_login": "alice"}],
                    "pagination": {"cursor": "next-page"},
                },
            ),
            httpx.Response(503, json={"message": "unavailable"}),
        )

        with pytest.raises(RuntimeError, match="snapshot unavailable"):
            await mock.client().get_vips("channel-1", "token")


@pytest.mark.asyncio
class TestRemoveVip:
    async def test_deletes_the_named_vip_with_broadcaster_token(self):
        mock = _MockAPI().route(
            "DELETE",
            "/helix/channels/vips",
            httpx.Response(204),
        )

        await mock.client().remove_vip("channel-1", "user-1", "broadcaster-token")

        request = mock.requests[-1]
        assert request.url.params["broadcaster_id"] == "channel-1"
        assert request.url.params["user_id"] == "user-1"
        assert request.headers["authorization"] == "Bearer broadcaster-token"

    async def test_raises_without_leaking_twitch_response_when_removal_fails(self):
        mock = _MockAPI().route(
            "DELETE",
            "/helix/channels/vips",
            httpx.Response(403, json={"message": "upstream details"}),
        )

        with pytest.raises(RuntimeError, match="VIP removal failed") as error:
            await mock.client().remove_vip("channel-1", "user-1", "token")

        assert "upstream details" not in str(error.value)


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

    def test_collaborator_url_can_use_identity_only_scope_and_callback(self):
        api = _MockAPI().client()
        url = api.generate_oauth_url(
            "signed-state",
            scopes=[],
            redirect_path="/api/auth/twitch/collaborator/callback",
        )

        assert "scope=" not in url
        assert "%2Fapi%2Fauth%2Ftwitch%2Fcollaborator%2Fcallback" in url


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

    async def test_exchange_uses_explicit_callback_path(self):
        mock = _MockAPI().route(
            "POST",
            "/oauth2/token",
            httpx.Response(
                200,
                json={"access_token": "user-at", "refresh_token": "user-rt", "scope": []},
            ),
        )
        mock.route("GET", "/helix/users", httpx.Response(200, json={"data": [{"id": "12345"}]}))
        api = mock.client()

        ok, _, _ = await api.exchange_code_for_token(
            "the-code", redirect_path="/api/auth/twitch/collaborator/callback"
        )

        assert ok is True
        token_request = next(r for r in mock.requests if r.method == "POST")
        assert (
            b"redirect_uri=https%3A%2F%2Fapi.example.com%2Fapi%2Fauth%2Ftwitch%2Fcollaborator%2Fcallback"
            in token_request.content
        )

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
        assert result.error_code == "provider_unavailable"


# ---------------------------------------------------------------------------
# validate/revoke user tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenValidation:
    async def test_valid_response_returns_identity_client_scopes_and_expiry(self):
        mock = _MockAPI().route(
            "GET",
            "/oauth2/validate",
            httpx.Response(
                200,
                json={
                    "client_id": "test-client-id",
                    "login": "alice",
                    "user_id": "42",
                    "scopes": ["chat:read", "chat:edit"],
                    "expires_in": 3600,
                },
            ),
        )

        result = await mock.client().validate_token_details("secret-token")

        assert result == TokenValidationResult(
            status="valid",
            client_id="test-client-id",
            login="alice",
            user_id="42",
            scopes=frozenset({"chat:read", "chat:edit"}),
            expires_in=3600,
        )
        assert mock.requests[0].headers["authorization"] == "OAuth secret-token"

    async def test_401_is_a_definite_invalid_token(self):
        mock = _MockAPI().route(
            "GET", "/oauth2/validate", httpx.Response(401, json={"message": "invalid"})
        )

        result = await mock.client().validate_token_details("secret-token")

        assert result.status == "invalid"
        assert result.error_code == "invalid_token"
        assert await mock.client().validate_token("secret-token") is False

    async def test_provider_failure_is_not_misclassified_as_invalid(self):
        mock = _MockAPI().route(
            "GET", "/oauth2/validate", httpx.Response(503, json={"message": "unavailable"})
        )

        result = await mock.client().validate_token_details("secret-token")

        assert result.status == "unavailable"
        assert result.error_code == "provider_unavailable"

    async def test_malformed_success_is_provider_unavailable(self):
        mock = _MockAPI().route(
            "GET", "/oauth2/validate", httpx.Response(200, json={"client_id": "test-client-id"})
        )

        result = await mock.client().validate_token_details("secret-token")

        assert result.status == "unavailable"
        assert result.error_code == "provider_unavailable"


@pytest.mark.asyncio
class TestTokenRevocation:
    async def test_200_reports_revoked_and_uses_form_encoded_secret(self):
        mock = _MockAPI().route("POST", "/oauth2/revoke", httpx.Response(200))

        result = await mock.client().revoke_access_token("secret-token")

        assert result == TokenRevocationResult(status="revoked")
        request = mock.requests[0]
        assert b"client_id=test-client-id" in request.content
        assert b"token=secret-token" in request.content

    async def test_400_is_idempotent_already_invalid(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/revoke", httpx.Response(400, json={"message": "invalid token"})
        )

        result = await mock.client().revoke_access_token("secret-token")

        assert result.status == "already_invalid"

    async def test_provider_failure_is_reported_without_upstream_details(self):
        mock = _MockAPI().route(
            "POST", "/oauth2/revoke", httpx.Response(503, json={"message": "internal detail"})
        )

        result = await mock.client().revoke_access_token("secret-token")

        assert result == TokenRevocationResult(
            status="unavailable", error_code="provider_unavailable"
        )


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
# get_user_emotes — platform-wide, paginated, owner_id preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetUserEmotes:
    async def test_follows_pagination_across_multiple_channels(self):
        """A bot subscribed to many channels can exceed one page — every page's
        emotes must come back, not just the first."""
        mock = _MockAPI().route(
            "GET",
            "/helix/chat/emotes/user",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "e1",
                            "name": "ChanAEmote",
                            "images": {"url_2x": "https://cdn/e1.png"},
                            "emote_type": "subscriptions",
                            "owner_id": "chan-a",
                        }
                    ],
                    "pagination": {"cursor": "CUR2"},
                },
            ),
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "e2",
                            "name": "ChanBEmote",
                            "images": {"url_2x": "https://cdn/e2.png"},
                            "emote_type": "subscriptions",
                            "owner_id": "chan-b",
                        }
                    ],
                    "pagination": {},
                },
            ),
        )
        api = mock.client()

        results = await api.get_user_emotes("current-channel", "user-tok", "bot-1")

        assert [r["owner_id"] for r in results] == ["chan-a", "chan-b"]

    async def test_preserves_owner_id_and_falls_back_to_globals_type(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/chat/emotes/user",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "g1",
                            "name": "Kappa",
                            "images": {"url_1x": "https://cdn/g1.png"},
                            "owner_id": "twitch",
                        }
                    ],
                    "pagination": {},
                },
            ),
        )
        api = mock.client()

        [emote] = await api.get_user_emotes("current-channel", "user-tok", "bot-1")

        assert emote == {
            "id": "g1",
            "name": "Kappa",
            "url": "https://cdn/g1.png",
            "emote_type": "globals",
            "owner_id": "twitch",
        }

    async def test_error_returns_empty_list(self):
        mock = _MockAPI().route(
            "GET", "/helix/chat/emotes/user", httpx.Response(401, json={"message": "no scope"})
        )
        api = mock.client()

        assert await api.get_user_emotes("current-channel", "user-tok", "bot-1") == []


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

    async def test_strict_login_lookup_batches_repeated_query_params(self):
        mock = _MockAPI().route("POST", "/oauth2/token", _app_token())
        mock.route(
            "GET",
            "/helix/users",
            httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "1", "login": "alice", "display_name": "Alice"},
                        {"id": "2", "login": "bob", "display_name": "Bob"},
                    ]
                },
            ),
        )
        api = mock.client()

        users = await api.get_users_by_logins_strict(["alice", "bob"])

        assert [user["id"] for user in users] == ["1", "2"]
        assert mock.requests[-1].url.params.get_list("login") == ["alice", "bob"]

    async def test_strict_lookup_distinguishes_upstream_failure_and_malformed_identity(self):
        failed = _MockAPI().route("POST", "/oauth2/token", _app_token())
        failed.route("GET", "/helix/users", httpx.Response(503, json={}))
        failed_api = failed.client()
        with pytest.raises(TwitchUsersLookupError):
            await failed_api.get_users_by_ids_strict(["1"])

        malformed = _MockAPI().route("POST", "/oauth2/token", _app_token())
        malformed.route("GET", "/helix/users", httpx.Response(200, json={"data": [{"id": "1"}]}))
        malformed_api = malformed.client()
        with pytest.raises(TwitchUsersLookupError):
            await malformed_api.get_users_by_ids_strict(["1"])

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

        followers = await api.fetch_all_followers("b1", "tok", "bot1")
        assert mock.requests[-1].url.params["moderator_id"] == "bot1"
        assert followers == [
            {
                "user_id": "1",
                "user_login": "a",
                "user_name": "A",
                "followed_at": "2021-01-01T00:00:00Z",
            }
        ]

    async def test_fetch_all_banned_maps_expiry_and_reason(self):
        mock = _MockAPI().route(
            "GET",
            "/helix/moderation/banned",
            httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "user_id": "1",
                            "user_login": "a",
                            "user_name": "A",
                            "expires_at": "2021-01-05T00:00:00Z",
                            "reason": "spam",
                        },
                        {"user_id": "2", "user_login": "b", "expires_at": "", "reason": ""},
                        {"user_login": "c"},
                    ],
                    "pagination": {},
                },
            ),
        )
        api = mock.client()

        banned = await api.fetch_all_banned("b1", "tok", "bot1")
        assert mock.requests[-1].url.params["moderator_id"] == "bot1"
        assert banned == [
            {
                "user_id": "1",
                "user_login": "a",
                "user_name": "A",
                "expires_at": "2021-01-05T00:00:00Z",
                "reason": "spam",
            },
            {
                "user_id": "2",
                "user_login": "b",
                "user_name": None,
                "expires_at": None,
                "reason": None,
            },
        ]


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_closes_http_client():
    api = _MockAPI().client()
    await api.close()
    assert api._http.is_closed
