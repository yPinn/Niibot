"""Tests for services/oauth_service.py — pure functions only (no DB)."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from api.services.oauth_service import decode_oauth_state, encode_oauth_state, find_or_create_user
from asyncpg.exceptions import UniqueViolationError

_SECRET = "test-secret-key"


class TestEncodeOauthState:
    def test_login_mode_no_uid(self):
        result = encode_oauth_state("login")
        decoded = decode_oauth_state(result)
        assert decoded == {"mode": "login"}

    def test_link_mode_with_uid(self):
        result = encode_oauth_state("link", user_id="abc-123")
        decoded = decode_oauth_state(result)
        assert decoded == {"mode": "link", "uid": "abc-123"}

    def test_no_uid_omits_key(self):
        result = encode_oauth_state("login", user_id=None)
        decoded = decode_oauth_state(result)
        assert "uid" not in decoded

    def test_output_is_string(self):
        assert isinstance(encode_oauth_state("login"), str)

    def test_url_safe_characters(self):
        """Encoded value must contain only URL-safe base64 chars."""
        result = encode_oauth_state("link", user_id="user+/=special")
        assert "+" not in result
        assert "/" not in result

    def test_with_secret_adds_nonce_and_sig(self):
        result = encode_oauth_state("login", secret=_SECRET)
        decoded = json.loads(base64.urlsafe_b64decode(result.encode()).decode())
        assert "nonce" in decoded
        assert "sig" in decoded

    def test_with_secret_nonce_is_random(self):
        r1 = encode_oauth_state("login", secret=_SECRET)
        r2 = encode_oauth_state("login", secret=_SECRET)
        d1 = json.loads(base64.urlsafe_b64decode(r1.encode()).decode())
        d2 = json.loads(base64.urlsafe_b64decode(r2.encode()).decode())
        assert d1["nonce"] != d2["nonce"]

    def test_with_secret_link_mode_roundtrip(self):
        result = encode_oauth_state("link", user_id="user-xyz", secret=_SECRET)
        decoded = decode_oauth_state(result, secret=_SECRET)
        assert decoded["mode"] == "link"
        assert decoded["uid"] == "user-xyz"
        assert "nonce" in decoded
        assert "sig" not in decoded  # sig is consumed during verification


class TestDecodeOauthState:
    def test_none_returns_login_default(self):
        assert decode_oauth_state(None) == {"mode": "login"}

    def test_empty_string_returns_login_default(self):
        assert decode_oauth_state("") == {"mode": "login"}

    def test_invalid_base64_returns_empty(self):
        assert decode_oauth_state("not-valid-base64!!!") == {}

    def test_valid_non_json_returns_empty(self):
        bad = base64.urlsafe_b64encode(b"this is not json").decode()
        assert decode_oauth_state(bad) == {}

    def test_roundtrip_preserves_extra_fields(self):
        """Extra keys encoded into state are preserved on decode (no-secret mode)."""
        data = {"mode": "link", "uid": "u1", "extra": "value"}
        encoded = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        assert decode_oauth_state(encoded) == data

    def test_with_secret_valid_state_succeeds(self):
        state = encode_oauth_state("login", secret=_SECRET)
        result = decode_oauth_state(state, secret=_SECRET)
        assert result["mode"] == "login"

    def test_with_secret_tampered_state_rejected(self):
        """Modifying any byte of the state must invalidate the HMAC."""
        state = encode_oauth_state("link", user_id="u1", secret=_SECRET)
        # Flip a character to simulate tampering
        tampered = state[:-4] + "AAAA"
        assert decode_oauth_state(tampered, secret=_SECRET) == {}

    def test_with_secret_missing_sig_rejected(self):
        """State without sig field must be rejected when secret is given."""
        data = {"mode": "login", "nonce": "abc123"}
        unsigned_state = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        assert decode_oauth_state(unsigned_state, secret=_SECRET) == {}

    def test_with_secret_wrong_secret_rejected(self):
        """State signed with a different secret must fail verification."""
        state = encode_oauth_state("login", secret=_SECRET)
        assert decode_oauth_state(state, secret="wrong-secret") == {}

    def test_with_secret_none_state_rejected(self):
        """Missing state must be rejected (not silently accepted) when secret is given."""
        assert decode_oauth_state(None, secret=_SECRET) == {}

    def test_with_secret_non_string_sig_rejected(self):
        """A non-string sig value must not reach hmac.compare_digest (would raise TypeError)."""
        data = {"mode": "login", "nonce": "abc", "sig": 12345}
        bad_state = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        # Must return {} without raising TypeError
        assert decode_oauth_state(bad_state, secret=_SECRET) == {}

    def test_no_secret_unsigned_state_still_works(self):
        """Without a secret, unsigned states decode normally (backward compat)."""
        data = {"mode": "login"}
        state = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        assert decode_oauth_state(state) == {"mode": "login"}


# ---------------------------------------------------------------------------
# find_or_create_user — DB race condition paths
# ---------------------------------------------------------------------------


def _make_pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _make_tx_cm() -> MagicMock:
    """Transaction context manager that re-raises exceptions (asyncpg default)."""
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)  # None == False → exception propagates
    return tx


@pytest.mark.asyncio
class TestFindOrCreateUser:
    async def test_fast_path_existing_account(self):
        """Existing linked account returns immediately without a transaction."""
        conn = AsyncMock()
        existing = MagicMock()
        existing.__getitem__ = lambda self, k: "existing-uuid" if k == "user_id" else None
        conn.fetchrow.return_value = existing
        conn.transaction = MagicMock(return_value=_make_tx_cm())

        pool = _make_pool_with_conn(conn)
        result = await find_or_create_user(pool, "twitch", "12345", "testuser")

        assert result == "existing-uuid"
        conn.transaction.assert_not_called()

    async def test_slow_path_creates_new_user(self):
        """No existing account → INSERT inside transaction → returns new user_id."""
        import uuid

        new_id = uuid.uuid4()
        conn = AsyncMock()
        user_row = MagicMock()
        user_row.__getitem__ = lambda self, k: new_id if k == "id" else None

        # fast path SELECT → None; INSERT INTO users → user_row
        conn.fetchrow.side_effect = [None, user_row]
        conn.execute.return_value = None
        conn.transaction = MagicMock(return_value=_make_tx_cm())

        pool = _make_pool_with_conn(conn)
        result = await find_or_create_user(pool, "twitch", "99999", "newuser")

        assert result == str(new_id)

    async def test_race_fallback_returns_winner_user_id(self):
        """UniqueViolationError → fallback SELECT finds the winner's user_id."""
        import uuid

        winner_id = uuid.uuid4()
        conn = AsyncMock()

        winner_row = MagicMock()
        winner_row.__getitem__ = lambda self, k: winner_id if k == "user_id" else None

        # fast path → None; INSERT users → some row; fallback SELECT → winner
        user_row = MagicMock()
        user_row.__getitem__ = lambda self, k: uuid.uuid4() if k == "id" else None
        conn.fetchrow.side_effect = [None, user_row, winner_row]
        conn.execute.side_effect = UniqueViolationError("unique constraint violation")
        conn.transaction = MagicMock(return_value=_make_tx_cm())

        pool = _make_pool_with_conn(conn)
        result = await find_or_create_user(pool, "twitch", "77777", "racewinner")

        assert result == str(winner_id)

    async def test_race_fallback_none_raises_runtime_error(self):
        """If winner's account is also gone after the race, RuntimeError is raised."""
        conn = AsyncMock()

        user_row = MagicMock()
        import uuid

        user_row.__getitem__ = lambda self, k: uuid.uuid4() if k == "id" else None

        # fast path → None; INSERT users → user_row; fallback SELECT → None (account gone)
        conn.fetchrow.side_effect = [None, user_row, None]
        conn.execute.side_effect = UniqueViolationError("unique constraint violation")
        conn.transaction = MagicMock(return_value=_make_tx_cm())

        pool = _make_pool_with_conn(conn)
        with pytest.raises(RuntimeError, match="Concurrent OAuth race"):
            await find_or_create_user(pool, "twitch", "00000", "ghost")
