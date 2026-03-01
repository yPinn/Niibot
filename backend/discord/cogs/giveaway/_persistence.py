"""File-based persistence for active giveaways."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GiveawayPersistence:
    """Manages loading and saving active_giveaways.json."""

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
            logger.info("Loaded %d active giveaways", len(result))
            return result
        except (OSError, ValueError, json.JSONDecodeError) as e:
            logger.error("Failed to load active giveaways: %s", e)
            return {}

    async def save(self, data: dict[int, dict]) -> None:
        """Persist current giveaway state to disk without blocking the event loop."""
        snapshot = dict(data)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._write_json, snapshot)
        except Exception as e:
            logger.error("Failed to save active giveaways: %s", e)

    def _write_json(self, data: dict) -> None:
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
