#!/usr/bin/env python3
"""Bot 帳號 emote 存取狀況。

Usage:
    cd backend && python scripts/tw_emotes.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import httpx
from dotenv import load_dotenv

_backend = Path(__file__).resolve().parent.parent
load_dotenv(_backend / "shared.env")
load_dotenv(_backend / "shared.env.local", override=True)
load_dotenv(_backend / "twitch" / ".env")

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
BOT_ID = os.getenv("BOT_ID", "")


async def _post(client: httpx.AsyncClient, url: str, **data) -> dict:
    r = await client.post(url, data=data)
    r.raise_for_status()
    return r.json()


async def _helix(client: httpx.AsyncClient, token: str, path: str, params) -> list[dict]:
    r = await client.get(
        f"https://api.twitch.tv/helix/{path}",
        headers={"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"},
        params=params,
    )
    r.raise_for_status()
    return r.json().get("data", [])


async def main() -> None:
    if not all([CLIENT_ID, CLIENT_SECRET, BOT_ID]):
        sys.exit("ERROR: TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET / BOT_ID not set")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("ERROR: DATABASE_URL not set")

    conn = await asyncpg.connect(db_url)
    bot_row = await conn.fetchrow(
        "SELECT refresh FROM tokens WHERE user_id = $1 AND token_type = 'bot'", BOT_ID
    )
    if not bot_row:
        await conn.close()
        sys.exit("ERROR: bot token not found")
    channels = await conn.fetch(
        "SELECT channel_id, channel_name FROM channels ORDER BY channel_name"
    )
    await conn.close()

    monitored_ids = {ch["channel_id"] for ch in channels}

    async with httpx.AsyncClient(timeout=15.0) as client:
        base = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        app_token = (
            await _post(
                client, "https://id.twitch.tv/oauth2/token", grant_type="client_credentials", **base
            )
        )["access_token"]
        bot_token = (
            await _post(
                client,
                "https://id.twitch.tv/oauth2/token",
                grant_type="refresh_token",
                refresh_token=bot_row["refresh"],
                **base,
            )
        )["access_token"]

        # bot 自身 login
        bot_info = await _helix(client, bot_token, "users", {"id": BOT_ID})
        bot_login = bot_info[0]["login"] if bot_info else BOT_ID

        # 監聽頻道：帶 broadcaster_id 查詢（才能看到 mod 授予的存取）
        channel_totals: dict[str, dict[str, int]] = {}
        bot_access: dict[str, dict[str, int]] = {}
        for ch in channels:
            cid = ch["channel_id"]
            ch_emotes = await _helix(client, app_token, "chat/emotes", {"broadcaster_id": cid})
            totals: dict[str, int] = {}
            ch_ids: dict[str, str] = {}
            for e in ch_emotes:
                t = e.get("emote_type", "")
                if t in ("follower", "subscriptions"):
                    totals[t] = totals.get(t, 0) + 1
                    ch_ids[e["id"]] = t
            channel_totals[cid] = totals

            accessible = await _helix(
                client, bot_token, "chat/emotes/user", {"user_id": BOT_ID, "broadcaster_id": cid}
            )
            accessible_ids = {e["id"] for e in accessible}
            acc: dict[str, int] = {}
            for eid, etype in ch_ids.items():
                if eid in accessible_ids:
                    acc[etype] = acc.get(etype, 0) + 1
            bot_access[cid] = acc

        # 全域查詢 → bot 有 follow/sub 關係的非監聽頻道
        global_emotes = await _helix(client, bot_token, "chat/emotes/user", {"user_id": BOT_ID})
        extra_access: dict[str, dict[str, int]] = {}
        for e in global_emotes:
            etype, owner = e.get("emote_type", ""), e.get("owner_id", "")
            if not owner or owner == BOT_ID or etype not in ("follower", "subscriptions"):
                continue
            if owner in monitored_ids:
                continue
            extra_access.setdefault(owner, {"follower": 0, "subscriptions": 0})
            extra_access[owner][etype] += 1

        extra_ids = list(extra_access)
        extra_logins: dict[str, str] = {}
        if extra_ids:
            users = await _helix(client, bot_token, "users", [("id", uid) for uid in extra_ids])
            extra_logins = {u["id"]: u["login"] for u in users}

    # ── Output ───────────────────────────────────────────────────────────────

    col = 20  # channel name column width
    cw = 8  # each data cell width: " N/ N ✓"

    def cell(has: int, total: int) -> str:
        if total == 0:
            return f"{'—':>{cw}}"
        mark = "✓" if has else "✗"
        return f"{has:>{cw - 5}d}/{total:<2d} {mark}  "

    # 分組：有任何存取 vs 無存取
    has_access = [ch for ch in channels if any(bot_access.get(ch["channel_id"], {}).values())]
    no_access = [ch for ch in channels if not any(bot_access.get(ch["channel_id"], {}).values())]

    sep = "─" * (col + cw * 2 + 6)

    print(f"\nBot: {bot_login} ({BOT_ID})\n")
    print(f"{'頻道':<{col}}  {'follower':>{cw}}  {'sub':>{cw}}")
    print(sep)

    for ch in has_access:
        cid, name = ch["channel_id"], ch["channel_name"]
        totals = channel_totals.get(cid, {})
        acc = bot_access.get(cid, {})
        print(
            f"{name:<{col}}  {cell(acc.get('follower', 0), totals.get('follower', 0))}"
            f"  {cell(acc.get('subscriptions', 0), totals.get('subscriptions', 0))}"
        )

    if has_access and no_access:
        print(sep)

    for ch in no_access:
        cid, name = ch["channel_id"], ch["channel_name"]
        totals = channel_totals.get(cid, {})
        acc = bot_access.get(cid, {})
        print(
            f"{name:<{col}}  {cell(acc.get('follower', 0), totals.get('follower', 0))}"
            f"  {cell(acc.get('subscriptions', 0), totals.get('subscriptions', 0))}"
        )

    if extra_access:
        print("\n額外關係（非監聽頻道）")
        print(sep)
        for oid in extra_ids:
            login = extra_logins.get(oid, oid)
            acc = extra_access[oid]
            tags = []
            if acc.get("follower"):
                tags.append(f"follow({acc['follower']})")
            if acc.get("subscriptions"):
                tags.append(f"sub({acc['subscriptions']})")
            print(f"  {login:<{col - 2}}  {' + '.join(tags)}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
