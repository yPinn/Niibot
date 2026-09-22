"""Local env secret generation contracts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "root_ensure_local_env", _ROOT / "scripts" / "ensure_local_env.py"
)
assert _SPEC is not None and _SPEC.loader is not None
ensure_local_env = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ensure_local_env
_SPEC.loader.exec_module(ensure_local_env)


def test_generates_valid_fernet_key_for_blank_assignment(tmp_path: Path) -> None:
    env_file = tmp_path / "shared.env"
    env_file.write_text(
        "DATABASE_URL=postgresql://localhost/db\nTWITCH_TOKEN_ENCRYPTION_KEY=\n",
        encoding="utf-8",
    )

    generated = ensure_local_env.ensure_twitch_token_encryption_key(env_file)

    assert generated is True
    key = next(
        line.split("=", 1)[1]
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("TWITCH_TOKEN_ENCRYPTION_KEY=")
    )
    Fernet(key.encode())
    assert "DATABASE_URL=postgresql://localhost/db" in env_file.read_text(encoding="utf-8")


def test_preserves_an_existing_valid_key(tmp_path: Path) -> None:
    env_file = tmp_path / "shared.env"
    existing_key = Fernet.generate_key().decode()
    original = f"TWITCH_TOKEN_ENCRYPTION_KEY={existing_key}\n"
    env_file.write_text(original, encoding="utf-8")

    generated = ensure_local_env.ensure_twitch_token_encryption_key(env_file)

    assert generated is False
    assert env_file.read_text(encoding="utf-8") == original


def test_rejects_invalid_existing_key_without_rotating_it(tmp_path: Path) -> None:
    env_file = tmp_path / "shared.env"
    original = "TWITCH_TOKEN_ENCRYPTION_KEY=not-a-fernet-key\n"
    env_file.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="not a valid Fernet key"):
        ensure_local_env.ensure_twitch_token_encryption_key(env_file)

    assert env_file.read_text(encoding="utf-8") == original


def test_appends_assignment_when_older_env_file_does_not_have_it(tmp_path: Path) -> None:
    env_file = tmp_path / "shared.env"
    env_file.write_text("DATABASE_URL=postgresql://localhost/db\n", encoding="utf-8")

    generated = ensure_local_env.ensure_twitch_token_encryption_key(env_file)

    assert generated is True
    assert "\nTWITCH_TOKEN_ENCRYPTION_KEY=" in env_file.read_text(encoding="utf-8")


def test_force_refresh_keeps_key_while_replacing_other_values(tmp_path: Path) -> None:
    env_file = tmp_path / "shared.env"
    example_file = tmp_path / "shared.env.example"
    existing_key = Fernet.generate_key().decode()
    env_file.write_text(
        f"DATABASE_URL=old\nTWITCH_TOKEN_ENCRYPTION_KEY={existing_key}\n",
        encoding="utf-8",
    )
    example_file.write_text(
        "DATABASE_URL=new\nTWITCH_TOKEN_ENCRYPTION_KEY=\nNEW_SETTING=\n",
        encoding="utf-8",
    )

    ensure_local_env.refresh_shared_env_preserving_key(example_file, env_file)

    refreshed = env_file.read_text(encoding="utf-8")
    assert "DATABASE_URL=new" in refreshed
    assert "NEW_SETTING=" in refreshed
    assert f"TWITCH_TOKEN_ENCRYPTION_KEY={existing_key}" in refreshed
