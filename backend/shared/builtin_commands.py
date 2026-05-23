"""Canonical builtin command definitions — single source of truth for both bot and API.

To add a new builtin command:
  1. Add it to BUILTIN_DEFS below.
  2. Add its description to BUILTIN_DESCRIPTIONS and PUBLIC_DESCRIPTIONS.
  3. Implement the handler in the relevant component file.

No database migration or per-channel seeding is required. New builtins
automatically appear for every channel on the next API or bot call.
"""

BUILTIN_DEFS: list[dict] = [
    # ── 通用互動 ──────────────────────────────────────────────────────────────
    {
        "command_name": "ping",
        "cooldown": 5,
        "aliases": "alive",
        "custom_response": "Pong! @$(user)",
    },
    {"command_name": "help", "cooldown": 5, "aliases": "commands,指令"},
    {"command_name": "condemn", "cooldown": 5, "aliases": "斥責"},
    # ── 資訊 ──────────────────────────────────────────────────────────────────
    {"command_name": "uptime", "cooldown": 10, "aliases": "開播時間"},
    {"command_name": "rank", "cooldown": 15, "aliases": "排名"},
    # ── 娛樂 ──────────────────────────────────────────────────────────────────
    {"command_name": "fortune", "cooldown": 5, "aliases": "運勢"},
    {"command_name": "tarot", "cooldown": 5, "aliases": "塔羅"},
    # ── 功能型（預設關閉，需手動啟用）────────────────────────────────────────
    {"command_name": "roll", "cooldown": 5, "aliases": "骰子", "enabled": False},
    {"command_name": "choose", "cooldown": 5, "aliases": "選擇", "enabled": False},
    {"command_name": "tft", "cooldown": 15, "aliases": "戰棋", "enabled": False},
    {"command_name": "crosshairs", "cooldown": 5, "aliases": "準星", "enabled": False},
]

BUILTIN_MAP: dict[str, dict] = {d["command_name"]: d for d in BUILTIN_DEFS}
BUILTIN_NAMES: frozenset[str] = frozenset(BUILTIN_MAP)

# Alias → canonical command_name reverse map
BUILTIN_ALIAS_MAP: dict[str, str] = {}
for _d in BUILTIN_DEFS:
    for _alias in (_d.get("aliases") or "").split(","):
        _alias = _alias.strip()
        if _alias:
            BUILTIN_ALIAS_MAP[_alias] = _d["command_name"]

# ── Descriptions (used by the API service layer) ──────────────────────────────

BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "ping": "確認機器人是否在線",
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "tft": "查詢聯盟戰棋排名",
    "fortune": "運勢占卜",
    "tarot": "塔羅牌占卜（可指定感情、事業、財運）",
    "condemn": "頻道反惡意言論聲明",
    "roll": "擲骰子（預設 d6，可指定面數）",
    "choose": "從選項中隨機挑選一個",
    "rank": "查詢本月個人活躍度排名",
    "crosshairs": "顯示頻道準星收藏頁面連結",
}

# Public /commands page — includes usage examples

PUBLIC_DESCRIPTIONS: dict[str, str] = {
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "tft": "查詢聯盟戰棋排名，用法：!tft <玩家名>#<tag>",
    "fortune": "運勢占卜",
    "tarot": "塔羅牌占卜，可指定分類：!塔羅 [感情/事業/財運]",
    "condemn": "頻道反惡意言論聲明",
    "roll": "擲骰子，用法：!roll [面數]（預設 d6）",
    "choose": "隨機選擇，用法：!choose 選項1 選項2 ...",
    "rank": "查詢本月個人活躍度排名",
    "crosshairs": "顯示頻道準星收藏頁面連結，用法：!crosshairs",
}
