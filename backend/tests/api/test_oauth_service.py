"""Tests for services/oauth_service.py — pure functions only (no DB).

The `find_or_create_user` helper that used to live here has been moved to
``services.identity_service.IdentityService``. See
``tests/api/test_identity_service.py`` for coverage of the new behaviour
(fast path, reconciliation, account linking, fresh signup, race conditions).
"""

import base64
import json

from api.services.oauth_service import decode_oauth_state, encode_oauth_state

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


# find_or_create_user tests moved to tests/api/test_identity_service.py
# alongside the new IdentityService coverage (fast path, reconciliation,
# account linking, fresh signup, race conditions).
