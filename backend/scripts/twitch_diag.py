#!/usr/bin/env python3
"""Twitch token / emote diagnostics.

    npm run nb -- twitch {tokens|emotes} [--env staging]
    uv run --directory backend python scripts/twitch_diag.py {tokens|emotes} [--env staging]

tokens — list stored tokens, validate each, show granted vs expected scopes
emotes — bot emote access per enabled channel
"""

from __future__ import annotations

import argparse
import asyncio
import os

import asyncpg
import httpx
from _lib import add_env_arg, database_url, ensure_backend_on_path, load_env, utf8_stdio

utf8_stdio()

# Populated by run() after load_env().
CLIENT_ID = ""
CLIENT_SECRET = ""
BOT_ID = ""
_BOT_SCOPES_SET: set[str] = set()
_BROADCASTER_SCOPES_SET: set[str] = set()


def _load_config(env: str) -> None:
    global CLIENT_ID, CLIENT_SECRET, BOT_ID, _BOT_SCOPES_SET, _BROADCASTER_SCOPES_SET
    load_env(env, service="twitch")
    ensure_backend_on_path()
    from twitch.core.config import BOT_SCOPES, BROADCASTER_SCOPES

    CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
    BOT_ID = os.getenv("BOT_ID", "")
    _BOT_SCOPES_SET = set(BOT_SCOPES)
    _BROADCASTER_SCOPES_SET = set(BROADCASTER_SCOPES)


# ── tokens ──────────────────────────────────────────────────────────────────


def _identify_role(scopes: set[str]) -> str:
    if "user:bot" in scopes:
        return "Bot"
    if "channel:bot" in scopes:
        return "Broadcaster"
    return "Unknown"


async def _tokens() -> None:
    conn = await asyncpg.connect(database_url())
    rows = await conn.fetch("SELECT user_id, token FROM tokens ORDER BY user_id")
    channels = await conn.fetch("SELECT channel_id, channel_name FROM channels")
    uid_to_name = {row["channel_id"]: row["channel_name"] for row in channels}

    print(f"=== Tokens ({len(rows)}) ===\n")

    tokens_data: list[dict] = []
    async with httpx.AsyncClient() as client:
        for row in rows:
            uid, token = row["user_id"], row["token"]
            try:
                r = await client.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token}"},
                )
                if r.status_code == 200:
                    d = r.json()
                    scopes = set(d.get("scopes", []))
                    tokens_data.append(
                        {
                            "uid": uid,
                            "login": d.get("login", "?"),
                            "scopes": scopes,
                            "role": _identify_role(scopes),
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

    # Bot first, then by uid.
    tokens_data.sort(key=lambda x: (0 if x.get("role") == "Bot" else 1, x["uid"]))

    for data in tokens_data:
        if data["status"] == "ok":
            scopes = data["scopes"]
            role = data["role"]
            print(f"{data['login']} ({data['uid']}) - {role}")
            print(f"  Scopes ({len(scopes)}):")
            for s in sorted(scopes):
                print(f"    - {s}")
            expected = (
                _BOT_SCOPES_SET
                if role == "Bot"
                else _BROADCASTER_SCOPES_SET
                if role == "Broadcaster"
                else None
            )
            if expected:
                missing = expected - scopes
                if missing:
                    print(f"  [WARN] missing scopes: {', '.join(sorted(missing))}")
            print()
        elif data["status"] == "expired":
            print(f"{uid_to_name.get(data['uid'], '?')} ({data['uid']}) - EXPIRED (401)\n")
        elif data["status"].startswith("error_"):
            code = data["status"].split("_")[1]
            print(f"{uid_to_name.get(data['uid'], '?')} ({data['uid']}) - ERROR ({code})\n")
        else:
            print(f"{uid_to_name.get(data['uid'], '?')} ({data['uid']}) - {data['status']}\n")


# ── emotes ──────────────────────────────────────────────────────────────────


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


async def _emotes() -> None:
    if not all([CLIENT_ID, CLIENT_SECRET, BOT_ID]):
        raise SystemExit("[ERROR] TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET / BOT_ID not set")

    conn = await asyncpg.connect(database_url())
    bot_row = await conn.fetchrow(
        "SELECT refresh FROM tokens WHERE user_id = $1 AND token_type = 'bot'", BOT_ID
    )
    if not bot_row:
        await conn.close()
        raise SystemExit("[ERROR] bot token not found")
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

        bot_info = await _helix(client, bot_token, "users", {"id": BOT_ID})
        bot_login = bot_info[0]["login"] if bot_info else BOT_ID

        # Monitored channels: query with broadcaster_id to see mod-granted access.
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

        # Global query → follow/sub relationships on non-monitored channels.
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

    has_access = [ch for ch in channels if any(bot_access.get(ch["channel_id"], {}).values())]
    no_access = [ch for ch in channels if not any(bot_access.get(ch["channel_id"], {}).values())]
    sep = "─" * (col + cw * 2 + 6)

    print(f"\nBot: {bot_login} ({BOT_ID})\n")
    print(f"{'channel':<{col}}  {'follower':>{cw}}  {'sub':>{cw}}")
    print(sep)

    def _row(ch) -> None:
        cid, name = ch["channel_id"], ch["channel_name"]
        totals = channel_totals.get(cid, {})
        acc = bot_access.get(cid, {})
        print(
            f"{name:<{col}}  {cell(acc.get('follower', 0), totals.get('follower', 0))}"
            f"  {cell(acc.get('subscriptions', 0), totals.get('subscriptions', 0))}"
        )

    for ch in has_access:
        _row(ch)
    if has_access and no_access:
        print(sep)
    for ch in no_access:
        _row(ch)

    if extra_access:
        print("\nExtra access (non-monitored channels)")
        print(sep)
        for oid in extra_ids:
            acc = extra_access[oid]
            tags = []
            if acc.get("follower"):
                tags.append(f"follow({acc['follower']})")
            if acc.get("subscriptions"):
                tags.append(f"sub({acc['subscriptions']})")
            print(f"  {extra_logins.get(oid, oid):<{col - 2}}  {' + '.join(tags)}")

    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Twitch token / emote diagnostics.")
    sub = parser.add_subparsers(dest="action", required=True)
    for name, helptext in (
        ("tokens", "List stored tokens, validate, show scopes"),
        ("emotes", "Show the bot's emote access per channel"),
    ):
        p = sub.add_parser(name, help=helptext)
        add_env_arg(p)
    return parser


async def _run(action: str, env: str) -> int:
    _load_config(env)
    await {"tokens": _tokens, "emotes": _emotes}[action]()
    return 0


def run(args: argparse.Namespace) -> int:
    # standalone parser sets `action`; nb sets `tw_action`
    action = getattr(args, "action", None) or getattr(args, "tw_action", "")
    assert action in ("tokens", "emotes"), f"unknown action {action!r}"
    try:
        return asyncio.run(_run(action, args.env))
    except KeyboardInterrupt:
        return 130


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
