#!/usr/bin/env python3
"""OAuth URL 生成工具"""

import os
import sys
from pathlib import Path
from urllib.parse import quote

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import BOT_SCOPES, BROADCASTER_SCOPES


def gen_url(cid: str, uri: str, scopes: list[str]) -> str:
    s = "+".join(s.replace(":", "%3A") for s in scopes)
    return f"https://id.twitch.tv/oauth2/authorize?client_id={cid}&redirect_uri={quote(uri, safe='')}&response_type=code&scope={s}"


cid = os.getenv("CLIENT_ID")
if not cid:
    print("錯誤: 未找到 CLIENT_ID")
    sys.exit(1)

uri = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:4343/oauth/callback")

print("Bot 帳號授權:")
print(gen_url(cid, uri, BOT_SCOPES))
print()
print("頻道授權:")
print(gen_url(cid, uri, BROADCASTER_SCOPES))
