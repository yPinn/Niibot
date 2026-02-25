"""Tests for services/oauth_service.py — pure functions only (no DB)."""

from api.services.oauth_service import decode_oauth_state, encode_oauth_state


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


class TestDecodeOauthState:
    def test_none_returns_login_default(self):
        assert decode_oauth_state(None) == {"mode": "login"}

    def test_empty_string_returns_login_default(self):
        assert decode_oauth_state("") == {"mode": "login"}

    def test_invalid_base64_returns_login_default(self):
        assert decode_oauth_state("not-valid-base64!!!") == {"mode": "login"}

    def test_valid_non_json_returns_login_default(self):
        import base64

        bad = base64.urlsafe_b64encode(b"this is not json").decode()
        assert decode_oauth_state(bad) == {"mode": "login"}

    def test_roundtrip_preserves_extra_fields(self):
        """Extra keys encoded into state are preserved on decode."""
        import base64
        import json

        data = {"mode": "link", "uid": "u1", "extra": "value"}
        encoded = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        assert decode_oauth_state(encoded) == data
