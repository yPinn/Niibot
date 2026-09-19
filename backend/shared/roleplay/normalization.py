"""Shared deterministic text normalization for validation and retrieval."""

from __future__ import annotations

import unicodedata


def normalize_roleplay_text(value: str) -> str:
    """Normalize width, case, and whitespace without language-specific stemming."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())
