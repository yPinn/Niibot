#!/usr/bin/env python3
"""Twitch OAuth 工具 — 生成授權 URL、接收回調、交換 token 並寫入資料庫。

Usage:
    python scripts/tw_oauth.py [bot|broadcaster]

    bot          — 用 BOT_SCOPES 授權 (niibot_ 帳號)
    broadcaster  — 用 BROADCASTER_SCOPES 授權 (頻道主帳號)
    (預設: 互動式選擇)
"""

from __future__ import annotations

import asyncio
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from urllib.parse import parse_qs, quote, urlparse

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import httpx
from dotenv import load_dotenv
from twitch.core.config import BOT_SCOPES, BROADCASTER_SCOPES

# Load twitch .env
load_dotenv(Path(__file__).resolve().parent.parent / "twitch" / ".env")

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
    """Exchange authorization code for access + refresh tokens."""
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
    """Validate token and return user info (user_id, login, scopes)."""
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


async def save_token(database_url: str, user_id: str, token: str, refresh: str) -> None:
    conn = await asyncpg.connect(database_url, ssl="require")
    try:
        await conn.execute(
            """
            INSERT INTO tokens (user_id, token, refresh)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                token      = EXCLUDED.token,
                refresh    = EXCLUDED.refresh,
                updated_at = NOW()
            """,
            user_id,
            token,
            refresh,
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

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

    server = HTTPServer(("127.0.0.1", LISTEN_PORT), _CallbackHandler)

    def serve() -> None:
        while not _callback_received.is_set():
            server.handle_request()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    _callback_received.wait(timeout=TIMEOUT_SECONDS)
    server.server_close()

    return _CallbackHandler.code, _CallbackHandler.error


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MODES = {
    "bot": ("Bot", BOT_SCOPES),
    "broadcaster": ("Broadcaster", BROADCASTER_SCOPES),
}


def main() -> None:
    # -- env validation --
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    database_url = os.getenv("DATABASE_URL")

    missing = []
    if not client_id:
        missing.append("CLIENT_ID")
    if not client_secret:
        missing.append("CLIENT_SECRET")
    if not database_url:
        missing.append("DATABASE_URL")
    if missing:
        fail(f"環境變數未設定: {', '.join(missing)}")

    # -- mode selection --
    mode = sys.argv[1] if len(sys.argv) > 1 else None

    if mode and mode not in MODES:
        fail(f"未知模式 '{mode}'。可用: bot, broadcaster")

    if mode is None:
        print()
        print(bold("Twitch OAuth 授權工具"))
        print()
        print(
            f"  {cyan('1')}  Bot 帳號      {dim('user:write:chat, moderator:manage:shoutouts …')}"
        )
        print(f"  {cyan('2')}  Broadcaster   {dim('channel:bot, channel:read:subscriptions …')}")
        print()
        choice = input(f"  選擇 {dim('[1/2]')}: ").strip()
        mode = "bot" if choice == "1" else "broadcaster"

    label, scopes = MODES[mode]
    total_steps = 4

    # -- step 1: generate URL --
    print()
    print(bold(f"=== {label} 授權 ==="))
    print()

    step(1, total_steps, "產生授權 URL")

    url = gen_url(client_id, REDIRECT_URI, scopes)  # type: ignore[arg-type]
    print(f"     {dim(url[:80])}{'…' if len(url) > 80 else ''}")

    try:
        webbrowser.open(url)
        print(f"     {green('✓')} 已在瀏覽器中開啟")
    except Exception:
        print(f"     {yellow('!')} 請手動在瀏覽器中開啟上方 URL")

    # -- step 2: wait for callback --
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

    # -- step 3: exchange + validate --
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

    # Scope diff check
    requested = set(scopes)
    granted = set(granted_scopes)
    missing_scopes = requested - granted
    if missing_scopes:
        print(f"     {yellow('!')} 缺少 scopes: {', '.join(sorted(missing_scopes))}")

    # -- step 4: save to DB --
    step(4, total_steps, "寫入資料庫")

    try:
        asyncio.run(save_token(database_url, user_id, access_token, refresh_token))  # type: ignore[arg-type]
    except Exception as e:
        fail(f"資料庫寫入失敗: {e}")

    print(f"     {green('✓')} tokens 表已更新")

    # -- done --
    print()
    print(f"  {green('✓')} {bold('完成')} — {login} 的 token 已更新，重啟 bot 後生效。")
    print()


if __name__ == "__main__":
    main()
