"""Canonical builtin command definitions — single source of truth for both bot and API.

To add a new builtin command:
  1. Add it to BUILTIN_DEFS below, in the right category block.
  2. Add its description to BUILTIN_DESCRIPTIONS (+ PUBLIC_DESCRIPTIONS if it
     should appear on the public /commands page).
  3. Implement the handler in the relevant component file.

BUILTIN_DEFS order == display order (dashboard + public page), so keep entries
grouped by category.

`"enabled": False` — default a command OFF when other chat bots
(Nightbot / StreamElements / Fossabot / ChiwaBot …) ship the same command
enabled by default. Two bots answering the same `!command` is worse than the
streamer opting in once. Niibot-original commands with no equivalent stay on.

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
    # `commands` 別名移除：與 Nightbot 預設 !commands 撞名（兩者都貼指令列表連結）。
    {"command_name": "help", "cooldown": 5, "aliases": "指令"},
    {"command_name": "condemn", "cooldown": 5, "aliases": "斥責"},
    # ── 頻道資訊 ──────────────────────────────────────────────────────────────
    # uptime 撞 Nightbot / StreamElements / Fossabot 預設指令 → 預設關；
    # rank 語意獨特（觀看時數＋留言活躍度，非點數排名）→ 預設開。
    {"command_name": "uptime", "cooldown": 10, "aliases": "開播時間", "enabled": False},
    {"command_name": "rank", "cooldown": 15, "aliases": "排名"},
    # ── 觀眾查詢（預設關閉：與 Nightbot / StreamElements / Fossabot /
    #    ChiwaBot 的同名指令衝突，交由實況主自行啟用）───────────────────────
    {"command_name": "followage", "cooldown": 15, "aliases": "追隨時間", "enabled": False},
    {"command_name": "subage", "cooldown": 15, "aliases": "訂閱資訊", "enabled": False},
    {"command_name": "subcount", "cooldown": 30, "aliases": "訂閱數", "enabled": False},
    {"command_name": "bits", "cooldown": 15, "aliases": "小奇點", "enabled": False},
    # ── 版主工具（預設關閉：!so 常與其他 bot 衝突；僅版主可用）─────────────
    {"command_name": "so", "cooldown": 5, "aliases": "推薦", "enabled": False},
    # ── 娛樂 ──────────────────────────────────────────────────────────────────
    {"command_name": "fortune", "cooldown": 5, "aliases": "運勢"},
    {"command_name": "tarot", "cooldown": 5, "aliases": "塔羅"},
    # ── 功能型（預設關閉，需手動啟用）────────────────────────────────────────
    {"command_name": "roll", "cooldown": 5, "aliases": "輪盤"},
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
    "roll": "聊天室共用輪盤，中彈 timeout 60 秒",
    "choose": "從選項中隨機挑選一個",
    "rank": "查詢本月個人活躍度排名",
    "followage": "查詢自己追隨頻道多久",
    "subage": "查詢自己的訂閱狀態",
    "subcount": "顯示頻道訂閱總數",
    "bits": "查詢自己的小奇點排名與總額",
    "so": "版主指令：對指定頻道執行推薦 shoutout",
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
    "roll": "誰是下一個？抽中禁言 10 分鐘，用法：!roll",
    "choose": "隨機選擇，用法：!choose 選項1 選項2 ...",
    "rank": "查詢本月個人活躍度排名",
    "followage": "查詢自己追隨頻道多久，用法：!followage",
    "subage": "查詢自己的訂閱狀態，用法：!subage",
    "subcount": "顯示頻道訂閱總數，用法：!subcount",
    "bits": "查詢自己的小奇點排名與總額，用法：!bits",
    "crosshairs": "顯示頻道準星收藏頁面連結，用法：!crosshairs",
}
