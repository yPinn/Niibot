"""Log-channel persistence for the events cog (atomic JSON on disk)."""

from __future__ import annotations

import json
import os
import tempfile

from core import RUNTIME_DIR

_LOG_CHANNELS_FILE = RUNTIME_DIR / "log_channels.json"


def _load_log_channels() -> dict[int, int]:
    try:
        with open(_LOG_CHANNELS_FILE, encoding="utf-8") as f:
            return {int(k): int(v) for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}


def _save_log_channels(data: dict[int, int]) -> None:
    payload = json.dumps({str(k): v for k, v in data.items()}, ensure_ascii=False, indent=2)
    dir_ = _LOG_CHANNELS_FILE.parent
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_, encoding="utf-8", delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name
    os.replace(tmp_path, _LOG_CHANNELS_FILE)
