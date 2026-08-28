#!/usr/bin/env python3
"""Download Twitch global role badge images to frontend/public/twitch-badges/.

Usage:
    npm run nb -- badges          # nb loads TWITCH_CLIENT_ID/SECRET from shared.env
    TWITCH_CLIENT_ID=xxx TWITCH_CLIENT_SECRET=yyy python scripts/badges.py

Flat badges (single version → /twitch-badges/{role}/{size}.png):
    broadcaster, lead_moderator, moderator, artist, vip, founder, partner, bot

Versioned badges (all versions → /twitch-badges/{role}/{version}/{size}.png):
    gift_leader  (versions: 1, 2, 3)
    sub_gifter   (versions: 1, 5, 10, 25, 50, 100, 250, 500, 1000)
    bits         (versions: 1, 100, 1000, 5000, 10000, 25000, 50000, 75000, 100000, ...)

Channel-specific badges (subscriber, founder images) — handled separately via the API.
"""

import os
import sys
from pathlib import Path

import httpx

# set_id → folder name, download only the "1" (or "0") version
FLAT_ROLES: dict[str, str] = {
    "broadcaster":    "broadcaster",
    "lead_moderator": "lead_moderator",
    "moderator":      "moderator",
    "artist-badge":   "artist",
    "vip":            "vip",
    "subscriber":     "subscriber",
    "founder":        "founder",
    "partner":        "partner",
    "bot-badge":      "bot",
}

# set_id → folder name, download every version into /{folder}/{version_id}/
VERSIONED_ROLES: dict[str, str] = {
    "sub-gift-leader": "gift_leader",
    "sub-gifter":      "sub_gifter",
    "bits":            "bits",
    "bits-leader":     "bits_leader",
}

OUT_DIR = Path(__file__).parent.parent / "frontend" / "public" / "twitch-badges"
HELIX = "https://api.twitch.tv/helix"
OAUTH = "https://id.twitch.tv/oauth2"
IMAGE_KEYS = [("image_url_1x", "1x.png"), ("image_url_2x", "2x.png"), ("image_url_4x", "4x.png")]


def get_app_token(client_id: str, client_secret: str) -> str:
    r = httpx.post(
        f"{OAUTH}/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def download_image(url: str, dest: Path) -> None:
    img = httpx.get(url, timeout=10)
    img.raise_for_status()
    dest.write_bytes(img.content)


def main() -> None:
    client_id = os.environ.get("TWITCH_CLIENT_ID", "")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("Error: TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set", file=sys.stderr)
        sys.exit(1)

    print("Fetching app token...")
    token = get_app_token(client_id, client_secret)

    print("Fetching global badges...")
    r = httpx.get(
        f"{HELIX}/chat/badges/global",
        headers={"Authorization": f"Bearer {token}", "Client-Id": client_id},
        timeout=10,
    )
    r.raise_for_status()
    badge_sets: list[dict] = r.json().get("data", [])

    downloaded = 0

    for badge_set in badge_sets:
        set_id: str = badge_set.get("set_id", "")
        versions: list[dict] = badge_set.get("versions", [])

        # ── Flat: single canonical version ────────────────────────────────────
        if set_id in FLAT_ROLES:
            folder = FLAT_ROLES[set_id]
            version = (
                next((v for v in versions if v.get("id") == "1"), None)
                or next((v for v in versions if v.get("id") == "0"), None)
                or (versions[0] if versions else None)
            )
            if not version:
                print(f"  ! {set_id}: no versions found, skipping")
                continue

            out_dir = OUT_DIR / folder
            out_dir.mkdir(parents=True, exist_ok=True)

            for url_key, filename in IMAGE_KEYS:
                url = version.get(url_key)
                if not url:
                    continue
                download_image(url, out_dir / filename)
                print(f"  ok {folder}/{filename}")
                downloaded += 1

        # ── Versioned: every version into its own subfolder ───────────────────
        elif set_id in VERSIONED_ROLES:
            folder = VERSIONED_ROLES[set_id]

            for version in versions:
                version_id: str = version.get("id", "")
                if not version_id:
                    continue

                out_dir = OUT_DIR / folder / version_id
                out_dir.mkdir(parents=True, exist_ok=True)

                for url_key, filename in IMAGE_KEYS:
                    url = version.get(url_key)
                    if not url:
                        continue
                    download_image(url, out_dir / filename)
                    print(f"  ok {folder}/{version_id}/{filename}")
                    downloaded += 1

    print(f"\nDone - {downloaded} files saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
