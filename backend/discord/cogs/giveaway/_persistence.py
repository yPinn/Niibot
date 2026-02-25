"""File-based persistence for active giveaways."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GiveawayPersistence:
    """Manages loading and saving active_giveaways.json."""

    def __init__(self, filepath: Path) -> None:
        self._filepath = filepath

    def load(self) -> dict[int, dict]:
        """Return stored giveaways keyed by message_id (int)."""
        if not self._filepath.exists():
            return {}
        try:
            with open(self._filepath, encoding="utf-8") as f:
                raw: dict = json.load(f)
            result = {int(k): v for k, v in raw.items()}
            logger.info(f"Loaded {len(result)} active giveaways")
            return result
        except Exception as e:
            logger.error(f"Failed to load active giveaways: {e}")
            return {}

    def save(self, data: dict[int, dict]) -> None:
        """Persist current giveaway state to disk."""
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save active giveaways: {e}")
