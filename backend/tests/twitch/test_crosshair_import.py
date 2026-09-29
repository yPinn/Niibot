"""Crosshair command modules stay importable without runtime credentials."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import TwitchBotSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_crosshair_module_import_does_not_require_twitch_credentials() -> None:
    env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "TWITCH_CLIENT_ID",
        "TWITCH_CLIENT_SECRET",
        "BOT_ID",
        "OWNER_ID",
    ):
        env.pop(key, None)
    env["ENVIRONMENT"] = "development"
    env["NIIBOT_RUNTIME_CONTEXT"] = "container"
    env["PYTHONPATH"] = os.pathsep.join((str(BACKEND_DIR), str(BACKEND_DIR / "twitch")))

    result = subprocess.run(
        [sys.executable, "-c", "from twitch.components.crosshair import CrosshairComponent"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_twitch_runtime_settings_still_require_app_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        TwitchBotSettings(
            database_url="postgresql://test:test@localhost/test",
            bot_id="bot-test",
            owner_id="owner-test",
            _env_file=None,
        )

    errors = {error["loc"][0] for error in exc_info.value.errors()}
    assert errors == {"twitch_client_id", "twitch_client_secret"}
