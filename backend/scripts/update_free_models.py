#!/usr/bin/env python3
"""Fetch current free models from OpenRouter and update twitch/free_models.json.

Usage (from backend/ directory):
    uv run python scripts/update_free_models.py
    uv run python scripts/update_free_models.py --with-uptime   # fetch uptime per model (slower)

The script:
- Fetches /api/v1/models and filters free (:free) models
- Optionally enriches each with uptime from /api/v1/models/{id}/endpoints
- Merges with existing free_models.json (preserves enabled/rpd/rpm/note)
- Adds newly appeared models as disabled (require manual review)
- Removes models that no longer exist on OpenRouter
- Writes sorted result back to twitch/free_models.json
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

MODELS_URL = "https://openrouter.ai/api/v1/models"
ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{model_id}/endpoints"
OUTPUT = Path(__file__).parent.parent / "data" / "free_models.json"

# Per-model RPD/RPM limits known from OpenRouter documentation.
# The API does not expose these; update manually when documented limits change.
KNOWN_LIMITS: dict[str, dict[str, int]] = {
    # Google models are restrictive on free tier
    "google/gemma-3-4b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-3-12b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-3-27b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-3n-e2b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-3n-e4b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-4-26b-a4b-it:free": {"rpd": 50, "rpm": 5},
    "google/gemma-4-31b-it:free": {"rpd": 50, "rpm": 5},
}
DEFAULT_LIMITS: dict[str, int] = {"rpd": 200, "rpm": 20}

# Models too small for meaningful chat responses — disabled by default
LOW_QUALITY_PATTERNS = [
    "1.2b",
    "3b-instruct",
    "4b-it",
    "venice-edition",  # uncensored model, unsuitable
]


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _fetch_uptime(model_id: str) -> float | None:
    """Return uptime_last_30m for the best (first) endpoint, or None."""
    url = ENDPOINTS_URL.format(model_id=urllib.request.quote(model_id, safe=""))
    try:
        data = _fetch(url)
        endpoints = data.get("data", {}).get("endpoints", [])
        for ep in endpoints:
            val = ep.get("uptime_last_30m")
            if val is not None:
                return float(val)
    except Exception:
        pass
    return None


def _is_low_quality(model_id: str) -> bool:
    lower = model_id.lower()
    return any(p in lower for p in LOW_QUALITY_PATTERNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update free_models.json")
    parser.add_argument(
        "--with-uptime",
        action="store_true",
        help="Fetch uptime for each model (adds ~1s per model)",
    )
    args = parser.parse_args()

    print("Fetching model list from OpenRouter...")
    data = _fetch(MODELS_URL)
    all_models = data.get("data", [])

    # Keep only :free tagged models with zero pricing
    free = {
        m["id"]: m
        for m in all_models
        if ":free" in m.get("id", "") and m.get("pricing", {}).get("prompt") == "0"
    }
    print(f"Found {len(free)} free models on OpenRouter")

    # Load existing file
    existing: dict[str, dict] = {}
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            old = json.load(f)
        for entry in old.get("models", []):
            existing[entry["id"]] = entry
        print(f"Loaded {len(existing)} existing entries from {OUTPUT.name}")

    merged: list[dict] = []
    added = removed = 0

    for model_id, model in free.items():
        name = model.get("name", model_id)
        # Strip "(free)" suffix from display name
        name = name.replace(" (free)", "").strip()

        limits = KNOWN_LIMITS.get(model_id, DEFAULT_LIMITS)

        uptime: float | None = None
        if args.with_uptime:
            uptime = _fetch_uptime(model_id)
            time.sleep(0.3)  # avoid hammering the API

        if model_id in existing:
            entry = dict(existing[model_id])
            entry["name"] = name  # keep name fresh
            if uptime is not None:
                entry["uptime_30m"] = uptime
            merged.append(entry)
        else:
            # New model — disable by default, require manual review
            is_low = _is_low_quality(model_id)
            entry = {
                "id": model_id,
                "name": name,
                "rpd": limits["rpd"],
                "rpm": limits["rpm"],
                "enabled": False,
                "note": "new — review before enabling" + (" | small model" if is_low else ""),
            }
            if uptime is not None:
                entry["uptime_30m"] = uptime
            merged.append(entry)
            added += 1
            print(f"  + NEW (disabled): {model_id}")

    # Count removed (in existing but no longer on OpenRouter)
    for model_id in existing:
        if model_id not in free:
            removed += 1
            print(f"  - REMOVED: {model_id}")

    # Sort enabled models:
    #   with uptime data  → uptime desc (null last), then rpd desc, then id
    #   without uptime    → rpd desc, then id
    # Disabled models always sorted after enabled ones.
    has_uptime_data = any("uptime_30m" in m for m in merged)

    def _sort_key(m: dict) -> tuple:
        enabled = not m.get("enabled", False)  # False sorts before True
        rpd = -m.get("rpd", 0)
        if has_uptime_data:
            uptime = m.get("uptime_30m")
            uptime_key = (uptime is None, -(uptime or 0))
            return (enabled, *uptime_key, rpd, m["id"])
        return (enabled, rpd, m["id"])

    merged.sort(key=_sort_key)

    result = {
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": merged,
    }

    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nDone. {len(merged)} models written to {OUTPUT} (+{added} new, -{removed} removed)")
    print("Review newly added models and set enabled=true as appropriate.")


if __name__ == "__main__":
    main()
