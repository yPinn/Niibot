"""Tests for secret-safe assistant health projection."""

from shared.assistant.health import primary_model_label


def test_primary_model_label_uses_first_ready_registration() -> None:
    status = {
        "providers": [
            {
                "provider": "gemini",
                "state": "misconfigured",
                "model": "gemini-3.5-flash",
                "reason": "missing_key",
            },
            {
                "provider": "groq",
                "state": "ready",
                "model": "openai/gpt-oss-120b",
                "reason": None,
            },
        ]
    }

    assert primary_model_label(status) == "groq/openai/gpt-oss-120b"


def test_primary_model_label_rejects_malformed_status() -> None:
    assert primary_model_label(None) is None
    assert primary_model_label({"providers": "not-a-list"}) is None
    assert primary_model_label({"providers": [{"state": "ready", "api_key": "secret"}]}) is None
