#!/usr/bin/env python3
"""顯示所有 token 資訊"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import httpx

from core.config import BOT_SCOPES, BROADCASTER_SCOPES

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


BOT_SCOPES_SET = set(BOT_SCOPES)
BROADCASTER_SCOPES_SET = set(BROADCASTER_SCOPES)


def identify_role(scopes: set[str]) -> str:
    """識別 token 角色"""
    if "user:bot" in scopes:
        return "Bot"
    if "channel:bot" in scopes:
        return "Broadcaster"
    return "Unknown"


async def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not found")
        return

    conn = await asyncpg.connect(db_url)
    rows = await conn.fetch("SELECT user_id, token FROM tokens ORDER BY user_id")

    # 建立 user_id -> channel_name 的映射（用於過期 token）
    channels = await conn.fetch("SELECT channel_id, channel_name FROM channels")
    uid_to_name = {row["channel_id"]: row["channel_name"] for row in channels}

    print(f"=== Tokens ({len(rows)}) ===\n")

    # 先處理 tokens 並分類
    tokens_data = []
    async with httpx.AsyncClient() as client:
        for row in rows:
            uid = row["user_id"]
            token = row["token"]

            try:
                r = await client.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token}"},
                )

                if r.status_code == 200:
                    d = r.json()
                    scopes = set(d.get("scopes", []))
                    role = identify_role(scopes)
                    tokens_data.append(
                        {
                            "uid": uid,
                            "login": d.get("login", "?"),
                            "scopes": scopes,
                            "role": role,
                            "status": "ok",
                        }
                    )
                elif r.status_code == 401:
                    tokens_data.append({"uid": uid, "status": "expired"})
                else:
                    tokens_data.append({"uid": uid, "status": f"error_{r.status_code}"})
            except Exception as e:
                tokens_data.append({"uid": uid, "status": f"exception: {e}"})

    await conn.close()

    # Bot 優先顯示
    tokens_data.sort(key=lambda x: (0 if x.get("role") == "Bot" else 1, x["uid"]))

    for data in tokens_data:
        if data["status"] == "ok":
            login = data["login"]
            uid = data["uid"]
            scopes = data["scopes"]
            role = data["role"]

            print(f"{login} ({uid}) - {role}")
            print(f"  Scopes ({len(scopes)}):")
            for s in sorted(scopes):
                print(f"    - {s}")

            if role == "Bot":
                missing = BOT_SCOPES_SET - scopes
                if missing:
                    print(f"  WARNING - MISSING: {', '.join(sorted(missing))}")
            elif role == "Broadcaster":
                missing = BROADCASTER_SCOPES_SET - scopes
                if missing:
                    print(f"  WARNING - MISSING: {', '.join(sorted(missing))}")

            print()

        elif data["status"] == "expired":
            uid = data["uid"]
            name = uid_to_name.get(uid, "?")
            print(f"{name} ({uid}) - EXPIRED (401)")
            print()
        elif data["status"].startswith("error_"):
            uid = data["uid"]
            name = uid_to_name.get(uid, "?")
            code = data["status"].split("_")[1]
            print(f"{name} ({uid}) - ERROR ({code})")
            print()
        else:
            uid = data["uid"]
            name = uid_to_name.get(uid, "?")
            print(f"{name} ({uid}) - {data['status']}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
