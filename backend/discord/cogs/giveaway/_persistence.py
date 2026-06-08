"""File-based persistence for active giveaways."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

LOGGER: logging.Logger = logging.getLogger(__name__)


class GiveawayPersistence:
    """Manages loading and saving giveaway_state.json."""

    def __init__(self, filepath: Path) -> None:
        self._filepath = filepath

    def load(self) -> dict[int, dict]:
        """Return stored giveaways keyed by message_id (int).

        Synchronous — safe to call from __init__ before the event loop starts.
        """
        if not self._filepath.exists():
            return {}
        try:
            with open(self._filepath, encoding="utf-8") as f:
                raw: dict = json.load(f)
            result = {int(k): v for k, v in raw.items()}
            LOGGER.info(f"Loaded {len(result)} active giveaways")
            return result
        except (OSError, ValueError, json.JSONDecodeError) as e:
            LOGGER.error(f"Failed to load active giveaways: {e}")
            return {}

    async def save(self, data: dict[int, dict]) -> None:
        """Persist current giveaway state to disk without blocking the event loop."""
        snapshot = dict(data)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._write_json, snapshot)
        except Exception as e:
            LOGGER.error(f"Failed to save active giveaways: {e}")

    def _write_json(self, data: dict) -> None:
        """Write atomically: write to a temp file then rename into place.

        os.replace() is atomic on both POSIX and Windows (Python 3.3+),
        so a crash mid-write never leaves a truncated or corrupt JSON file.
        """
        dir_ = self._filepath.parent
        with tempfile.NamedTemporaryFile(
            "w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_path = f.name
        os.replace(tmp_path, self._filepath)
