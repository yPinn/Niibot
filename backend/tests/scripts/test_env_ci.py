"""CI env rendering contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from base64 import urlsafe_b64encode
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("env_ci", ROOT / "scripts" / "env" / "ci.py")
assert SPEC is not None and SPEC.loader is not None
ci = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ci
SPEC.loader.exec_module(ci)

VALID_FERNET_KEY = urlsafe_b64encode(b"0" * 32).decode()


def _manifest() -> dict:
    return {
        "required_secrets": ["REQUIRED_SECRET"],
        "required_variables": ["PROJECT_DIR"],
        "ci_groups": {
            "groq": {
                "members": ["GROQ_API_KEY", "GROQ_MODEL"],
                "activators": ["GROQ_API_KEY"],
            },
            "nightbot": {
                "members": ["NIGHTBOT_CLIENT_ID", "NIGHTBOT_CLIENT_SECRET"],
                "activators": ["NIGHTBOT_CLIENT_ID", "NIGHTBOT_CLIENT_SECRET"],
            },
        },
        "ci": {
            "REQUIRED_SECRET": {
                "file": "api",
                "source": "secret:REQUIRED_SECRET",
                "scope": "env",
                "conditional": False,
            },
            "PROJECT_DIR": {
                "source": "var:PROJECT_DIR",
                "scope": "env",
                "conditional": False,
            },
            "GROQ_API_KEY": {
                "file": "shared",
                "source": "secret:GROQ_API_KEY",
                "scope": "base",
                "conditional": True,
            },
            "GROQ_MODEL": {
                "file": "shared",
                "source": "var:GROQ_MODEL",
                "scope": "base",
                "conditional": True,
                "default": "default-model",
            },
            "NIGHTBOT_CLIENT_ID": {
                "file": "api",
                "source": "var:NIGHTBOT_CLIENT_ID",
                "scope": "env",
                "conditional": True,
            },
            "NIGHTBOT_CLIENT_SECRET": {
                "file": "api",
                "source": "secret:NIGHTBOT_CLIENT_SECRET",
                "scope": "env",
                "conditional": True,
            },
        },
    }


def _render(*, secrets: dict[str, str] | None = None, variables: dict[str, str] | None = None):
    return ci.render_files(
        _manifest(),
        secrets={"REQUIRED_SECRET": "required", **(secrets or {})},
        variables={"PROJECT_DIR": "/srv/niibot", **(variables or {})},
        deploy_environment="staging",
    )


def test_inactive_group_ignores_a_stale_non_activating_model() -> None:
    rendered = _render(variables={"GROQ_MODEL": "stale-model"})

    assert rendered["backend/shared.stg.env"] == ""


def test_active_group_uses_the_registry_model_default() -> None:
    rendered = _render(secrets={"GROQ_API_KEY": "groq-secret"})

    assert "GROQ_API_KEY='groq-secret'\n" in rendered["backend/shared.stg.env"]
    assert "GROQ_MODEL='default-model'\n" in rendered["backend/shared.stg.env"]


def test_active_group_treats_quoted_empty_model_as_unset() -> None:
    rendered = _render(
        secrets={"GROQ_API_KEY": "groq-secret"},
        variables={"GROQ_MODEL": "''"},
    )

    assert "GROQ_MODEL='default-model'\n" in rendered["backend/shared.stg.env"]


def test_incomplete_group_fails_without_exposing_values() -> None:
    with pytest.raises(ValueError) as exc_info:
        _render(variables={"NIGHTBOT_CLIENT_ID": "private-client-id"})

    message = str(exc_info.value)
    assert message == "incomplete group nightbot: missing NIGHTBOT_CLIENT_SECRET"
    assert "private-client-id" not in message


@pytest.mark.parametrize(
    ("secrets", "variables", "missing"),
    [
        ({"REQUIRED_SECRET": ""}, None, "REQUIRED_SECRET"),
        ({"REQUIRED_SECRET": "''"}, None, "REQUIRED_SECRET"),
        (None, {"PROJECT_DIR": ""}, "PROJECT_DIR"),
    ],
)
def test_required_values_fail_before_rendering(
    secrets: dict[str, str] | None,
    variables: dict[str, str] | None,
    missing: str,
) -> None:
    with pytest.raises(ValueError, match=missing):
        _render(secrets=secrets, variables=variables)


def test_multiline_values_are_rejected_without_exposing_the_value() -> None:
    with pytest.raises(ValueError) as exc_info:
        _render(secrets={"REQUIRED_SECRET": "first\nsecond"})

    assert str(exc_info.value) == "value for REQUIRED_SECRET contains a newline"
    assert "first" not in str(exc_info.value)


def test_fernet_values_are_validated_without_exposing_the_value() -> None:
    manifest = _manifest()
    manifest["required_secrets"].append("ENCRYPTION_KEY")
    manifest["ci"]["ENCRYPTION_KEY"] = {
        "file": "shared",
        "source": "secret:ENCRYPTION_KEY",
        "scope": "env",
        "conditional": False,
        "format": "fernet",
    }

    with pytest.raises(ValueError) as exc_info:
        ci.render_files(
            manifest,
            secrets={"REQUIRED_SECRET": "required", "ENCRYPTION_KEY": "invalid-secret"},
            variables={"PROJECT_DIR": "/srv/niibot"},
            deploy_environment="staging",
        )

    assert str(exc_info.value) == "invalid Fernet key: ENCRYPTION_KEY"
    assert "invalid-secret" not in str(exc_info.value)

    rendered = ci.render_files(
        manifest,
        secrets={"REQUIRED_SECRET": "required", "ENCRYPTION_KEY": VALID_FERNET_KEY},
        variables={"PROJECT_DIR": "/srv/niibot"},
        deploy_environment="staging",
    )
    assert "ENCRYPTION_KEY=" in rendered["backend/shared.stg.env"]


def test_generated_manifest_renders_all_deploy_files() -> None:
    manifest = json.loads((ROOT / "env.manifest.json").read_text(encoding="utf-8"))
    secrets = {
        key: VALID_FERNET_KEY if manifest["ci"][key].get("format") == "fernet" else "test-secret"
        for key in manifest["required_secrets"]
    }
    variables = {key: "test-value" for key in manifest["required_variables"]}

    rendered = ci.render_files(
        manifest,
        secrets=secrets,
        variables=variables,
        deploy_environment="staging",
    )

    assert set(rendered) == {
        ".env.stg",
        "backend/shared.stg.env",
        "backend/api/.env.stg",
        "backend/twitch/.env.stg",
        "backend/discord/.env.stg",
    }
    assert "ENVIRONMENT='staging'\n" in rendered["backend/shared.stg.env"]
