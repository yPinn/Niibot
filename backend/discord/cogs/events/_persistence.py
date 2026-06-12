"""Log-channel persistence for the events cog (atomic JSON on disk)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from core import RUNTIME_DIR

_LOG_CHANNELS_FILE = RUNTIME_DIR / "log_channels.json"
_IGNORED_ROLES_FILE = RUNTIME_DIR / "log_ignored_roles.json"


def _atomic_write(path: Path, payload: str) -> None:
    """Write *payload* to *path* atomically (temp file + os.replace)."""
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, encoding="utf-8", delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def _load_log_channels() -> dict[int, int]:
    try:
        with open(_LOG_CHANNELS_FILE, encoding="utf-8") as f:
            return {int(k): int(v) for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}


def _save_log_channels(data: dict[int, int]) -> None:
    payload = json.dumps({str(k): v for k, v in data.items()}, ensure_ascii=False, indent=2)
    _atomic_write(_LOG_CHANNELS_FILE, payload)


def _load_ignored_roles() -> dict[int, set[int]]:
    try:
        with open(_IGNORED_ROLES_FILE, encoding="utf-8") as f:
            return {int(k): {int(r) for r in v} for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def _save_ignored_roles(data: dict[int, set[int]]) -> None:
    payload = json.dumps({str(k): sorted(v) for k, v in data.items()}, ensure_ascii=False, indent=2)
    _atomic_write(_IGNORED_ROLES_FILE, payload)
