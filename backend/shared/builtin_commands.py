"""Canonical builtin command definitions — single source of truth for both bot and API.

To add a new builtin command:
  1. Add it to BUILTIN_DEFS below.
  2. Add its description to BUILTIN_DESCRIPTIONS and PUBLIC_DESCRIPTIONS.
  3. Implement the handler in the relevant component file.

No database migration or per-channel seeding is required. New builtins
automatically appear for every channel on the next API or bot call.
"""

BUILTIN_DEFS: list[dict] = [
    {
        "command_name": "hi",
        "cooldown": 5,
        "aliases": "hello,hey",
        "custom_response": "你好,$(user)!",
    },
    {"command_name": "help", "cooldown": 5, "aliases": "commands,指令"},
    {"command_name": "uptime", "cooldown": 5, "aliases": "開播時間"},
    {"command_name": "condemn", "cooldown": 10, "aliases": "斥責"},
    {"command_name": "fortune", "cooldown": 5, "aliases": "運勢"},
    {"command_name": "tarot", "cooldown": 5, "aliases": "塔羅"},
    {"command_name": "ai", "cooldown": 15, "aliases": "問"},
    {"command_name": "tft", "cooldown": 5, "aliases": "戰棋"},
]

# O(1) lookup by canonical command name
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
    "hi": "向聊天室打招呼",
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "ai": "向 AI 提問",
    "tft": "查詢聯盟戰棋排名",
    "fortune": "運勢占卜",
    "tarot": "塔羅牌占卜（可指定感情、事業、財運）",
    "condemn": "頻道反惡意言論聲明",
}

# Public /commands page — includes usage examples
PUBLIC_DESCRIPTIONS: dict[str, str] = {
    "hi": "向聊天室打招呼",
    "help": "顯示所有可用指令列表",
    "uptime": "查看目前已開播多久",
    "ai": "向 AI 提問，用法：!問 <問題>",
    "tft": "查詢聯盟戰棋排名，用法：!tft <玩家名>#<tag>",
    "fortune": "運勢占卜",
    "tarot": "塔羅牌占卜，可指定分類：!塔羅 [感情/事業/財運]",
    "condemn": "頻道反惡意言論聲明",
}
