"""CLI smoke contracts for the Twitch credential migration tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_help_loads_from_the_documented_backend_workdir() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/encrypt_twitch_tokens.py", "--help"],
        cwd=_BACKEND_DIR,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--repair-missing-envelopes" in result.stdout
