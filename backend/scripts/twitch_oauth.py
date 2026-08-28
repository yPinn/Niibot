#!/usr/bin/env python3
"""Twitch OAuth 工具 — 開瀏覽器授權、收 callback、換 token 寫入 DB tokens 表。

何時用: 首次設定、token 被撤銷、或新增 scope 後需重新授權。跑完重啟對應 bot 生效。
前置: Twitch dev console 的 OAuth Redirect URLs 需含 http://localhost:3000/callback

用法（擇一；--env / --role 省略則進互動選單）:
    npm run nb -- twitch oauth [--env prod|staging] [--role bot|broadcaster]
    uv run --directory backend python scripts/twitch_oauth.py [--env ...] [--role ...]

    --env    prod    → shared.env         + twitch/.env
             staging → shared.staging.env + twitch/.env.staging
    --role   bot | broadcaster   決定請求的 scope 集合（見 twitch.core.config）

直接跑時亦接受舊式位置參數（順序不拘），例: ... scripts/twitch_oauth.py staging bot
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ for twitch.*

import asyncpg
import httpx
from _lib import load_env, utf8_stdio
from twitch.core.config import BOT_SCOPES, BROADCASTER_SCOPES

utf8_stdio()

LISTEN_PORT = 3000
REDIRECT_URI = f"http://localhost:{LISTEN_PORT}/callback"
TIMEOUT_SECONDS = 120

# ---------------------------------------------------------------------------
# Terminal colours (auto-disable on non-TTY)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty() and os.name != "nt" or os.getenv("FORCE_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def dim(t: str) -> str:
    return _c("2", t)


def bold(t: str) -> str:
    return _c("1", t)


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def red(t: str) -> str:
    return _c("31", t)


def cyan(t: str) -> str:
    return _c("36", t)


def step(n: int, total: int, msg: str) -> None:
    print(f"  {dim(f'[{n}/{total}]')} {msg}")


def fail(msg: str) -> None:
    print(f"\n  {red('✗')} {msg}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Twitch API helpers (sync httpx — script runs sequentially)
# ---------------------------------------------------------------------------

_http = httpx.Client(timeout=10)


def exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    resp = _http.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    return resp.json()


def validate_token(access_token: str) -> dict:
    resp = _http.get(
        "https://id.twitch.tv/oauth2/validate",
        headers={"Authorization": f"OAuth {access_token}"},
    )
    resp.raise_for_status()
    return resp.json()


def gen_url(client_id: str, redirect_uri: str, scopes: list[str]) -> str:
    scope_str = "+".join(s.replace(":", "%3A") for s in scopes)
    return (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&scope={scope_str}"
        f"&force_verify=true"
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


async def save_token(
    database_url: str,
    user_id: str,
    token: str,
    refresh: str,
    scopes: list[str],
    token_type: str,
) -> None:
    conn = await asyncpg.connect(database_url, ssl="prefer")
    try:
        await conn.execute(
            """
            INSERT INTO tokens (user_id, token, refresh, scopes, token_type)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, token_type) DO UPDATE SET
                token           = EXCLUDED.token,
                refresh         = EXCLUDED.refresh,
                scopes          = EXCLUDED.scopes,
                requires_reauth = FALSE,
                updated_at      = NOW()
            """,
            user_id,
            token,
            refresh,
            " ".join(scopes) if scopes else None,
            token_type,
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------


class _DualStackHTTPServer(HTTPServer):
    """Listens on IPv6 with dual-stack (IPv4+IPv6) where available.

    On macOS, `localhost` resolves to ::1 (IPv6), so a plain IPv4-only server
    would refuse the OAuth callback redirect. Falls back to IPv4 if unsupported.
    """

    def __init__(self, port: int, handler: type) -> None:
        if socket.has_dualstack_ipv6():
            self.address_family = socket.AF_INET6
            super().__init__(("", port), handler)
        else:
            super().__init__(("127.0.0.1", port), handler)


_callback_received = Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)

        if "error" in params:
            _CallbackHandler.error = params["error"][0]
            self._html(f"<h2>授權失敗</h2><p>{params['error'][0]}</p>")
            _callback_received.set()
            return

        code = params.get("code", [None])[0]
        if code:
            _CallbackHandler.code = code
            self._html(
                "<h2 style='color:#22c55e'>授權成功</h2><p>可以關閉此頁面，回到終端機查看結果。</p>"
            )
            _callback_received.set()
        else:
            self._html("<h2>缺少授權碼</h2>", status=400)

    def _html(self, body: str, *, status: int = 200) -> None:
        page = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>body{font-family:system-ui;display:flex;justify-content:center;"
            "align-items:center;height:100vh;margin:0;background:#0e0e10;color:#efeff1}</style>"
            f"</head><body><div>{body}</div></body></html>"
        )
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())

    def log_message(self, *_a) -> None:
        pass


def wait_for_callback() -> tuple[str | None, str | None]:
    """Start local server, block until callback or timeout. Returns (code, error)."""
    _CallbackHandler.code = None
    _CallbackHandler.error = None
    _callback_received.clear()

    server = _DualStackHTTPServer(LISTEN_PORT, _CallbackHandler)

    def serve() -> None:
        while not _callback_received.is_set():
            server.handle_request()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    _callback_received.wait(timeout=TIMEOUT_SECONDS)
    server.server_close()

    return _CallbackHandler.code, _CallbackHandler.error


# ---------------------------------------------------------------------------
# Config tables  (env-file resolution lives in _lib.load_env)
# ---------------------------------------------------------------------------

ENVS = ("prod", "staging")

ROLES: dict[str, tuple[str, list[str]]] = {
    "bot": ("Bot", BOT_SCOPES),
    "broadcaster": ("Broadcaster", BROADCASTER_SCOPES),
}


# ---------------------------------------------------------------------------
# Arg parsing + interactive prompts
# ---------------------------------------------------------------------------


def _pick(prompt: str, choices: dict[str, str]) -> str:
    """Print numbered choices and return the selected key."""
    for i, (key, label) in enumerate(choices.items(), 1):
        print(f"  {cyan(str(i))}  {key:<14}{dim(label)}")
    print()
    keys = list(choices)
    while True:
        raw = input(f"  {prompt} {dim(f'[1–{len(keys)}]')}: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1]
        if raw in keys:
            return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Twitch OAuth token generator.")
    parser.add_argument("--env", choices=ENVS, help="prod | staging (interactive if omitted)")
    parser.add_argument(
        "--role", choices=tuple(ROLES), help="bot | broadcaster (interactive if omitted)"
    )
    # Legacy positional form: `twitch_oauth.py staging bot` (order-independent).
    parser.add_argument("legacy", nargs="*", help=argparse.SUPPRESS)
    return parser


def _resolve_env_role(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve env + role from flags / legacy positionals; prompt for any missing."""
    env: str | None = args.env
    role: str | None = args.role
    for tok in getattr(args, "legacy", []):  # legacy positionals — standalone only
        if tok in ENVS:
            env = env or tok
        elif tok in ROLES:
            role = role or tok
        else:
            fail(f"未知參數: {tok}\n  可用環境: {', '.join(ENVS)}\n  可用角色: {', '.join(ROLES)}")

    if env is None or role is None:
        print(f"\n{bold('Twitch OAuth 授權工具')}\n")
    if env is None:
        env = _pick(
            "選擇環境",
            {
                "prod": "shared.env + twitch/.env",
                "staging": "shared.staging.env + twitch/.env.staging",
            },
        )
    if role is None:
        role = _pick(
            "選擇角色",
            {
                "bot": "user:write:chat, moderator:manage:shoutouts …",
                "broadcaster": "channel:bot, channel:read:subscriptions …",
            },
        )
    return env, role


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    env, role = _resolve_env_role(args)
    load_env(env, service="twitch")

    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    database_url = os.getenv("DATABASE_URL")

    missing = [
        k
        for k, v in {
            "TWITCH_CLIENT_ID": client_id,
            "TWITCH_CLIENT_SECRET": client_secret,
            "DATABASE_URL": database_url,
        }.items()
        if not v
    ]
    if missing:
        fail(f"環境變數未設定: {', '.join(missing)}")

    label, scopes = ROLES[role]
    env_tag = f" {yellow('[STAGING]')}" if env == "staging" else ""
    total_steps = 4

    print()
    print(bold(f"=== {label} 授權{env_tag} ==="))
    print()

    step(1, total_steps, "產生授權 URL")

    url = gen_url(client_id, REDIRECT_URI, scopes)  # type: ignore[arg-type]
    print(f"     {dim(url[:80])}{'…' if len(url) > 80 else ''}")

    try:
        webbrowser.open(url)
        print(f"     {green('✓')} 已在瀏覽器中開啟")
    except Exception:
        print(f"     {yellow('!')} 請手動在瀏覽器中開啟上方 URL")

    step(
        2,
        total_steps,
        f"等待授權回調 {dim(f'(http://localhost:{LISTEN_PORT}/callback, {TIMEOUT_SECONDS}s timeout)')}",
    )

    code, error = wait_for_callback()

    if error:
        fail(f"Twitch 回傳錯誤: {error}")
    if not code:
        fail(f"超時 ({TIMEOUT_SECONDS}s)，未收到授權回調")

    print(f"     {green('✓')} 收到授權碼")

    step(3, total_steps, "交換並驗證 Token")

    try:
        token_data = exchange_code(client_id, client_secret, code)  # type: ignore[arg-type]
    except httpx.HTTPStatusError as e:
        fail(f"Token 交換失敗: {e.response.text}")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    try:
        info = validate_token(access_token)
    except httpx.HTTPStatusError as e:
        fail(f"Token 驗證失敗: {e.response.text}")

    user_id = info.get("user_id", "unknown")
    login = info.get("login", "unknown")
    granted_scopes = info.get("scopes", [])

    print(f"     {green('✓')} {bold(login)} {dim(f'(ID: {user_id})')}")
    print(f"     {dim(f'Scopes: {len(granted_scopes)} granted')}")

    missing_scopes = set(scopes) - set(granted_scopes)
    if missing_scopes:
        print(f"     {yellow('!')} 缺少 scopes: {', '.join(sorted(missing_scopes))}")

    step(4, total_steps, "寫入資料庫")

    assert database_url is not None
    try:
        asyncio.run(
            save_token(database_url, user_id, access_token, refresh_token, granted_scopes, role)
        )
    except Exception as e:
        fail(f"資料庫寫入失敗: {e}")

    print(f"     {green('✓')} tokens 表已更新")

    print()
    print(f"  {green('✓')} {bold('完成')} — {login} 的 token 已更新，重啟 bot 後生效。")
    print()
    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
