"""Canonical builtin command definitions — single source of truth for both bot and API.

To add a new builtin command:
  1. Add it to BUILTIN_DEFS below with a "category" from BUILTIN_CATEGORIES,
     placed next to the other entries of that category.
  2. Add its description to BUILTIN_DESCRIPTIONS (+ PUBLIC_DESCRIPTIONS if it
     should appear on the public /commands page).
  3. Implement the handler in the relevant component file.

BUILTIN_DEFS order == display order (dashboard + public page). Entries must stay
grouped so every category's rows are contiguous — the dashboard renders a group
header each time "category" changes, it does not sort or bucket. BUILTIN_CATEGORIES
insertion order is the category display order.

`"min_role"` — optional, defaults to `"everyone"`. Set it (e.g. `"moderator"`)
for commands that should be gated by default; `_make_virtual` reads it so the
dashboard shows the real permission and the streamer can loosen it there.

`"enabled": False` — default a command OFF when other chat bots
(Nightbot / StreamElements / Fossabot / ChiwaBot …) ship the same command
enabled by default. Two bots answering the same `!command` is worse than the
streamer opting in once. Niibot-original commands with no equivalent stay on.

No database migration or per-channel seeding is required. New builtins
automatically appear for every channel on the next API or bot call.
"""

# Category key → display label. Insertion order == the order categories appear
# in the dashboard. Every key must be used by at least one BUILTIN_DEFS entry.
BUILTIN_CATEGORIES: dict[str, str] = {
    "common": "常用互動",
    "viewer": "觀眾查詢",
    "fun": "娛樂互動",
    "game": "遊戲工具",
    "broadcaster": "實況主工具",
    "moderator": "Mod 工具",
}

BUILTIN_DEFS: list[dict] = [
    # ── 常用互動（觀眾最常需要找到的入口優先）───────────────────────────────
    # `commands` 別名移除：與 Nightbot 預設 !commands 撞名（兩者都貼指令列表連結）。
    {"command_name": "help", "category": "common", "cooldown": 5, "aliases": "指令"},
    {
        "command_name": "checkin",
        "category": "common",
        "cooldown": 5,
        "aliases": "簽到",
    },
    # uptime 撞 Nightbot / StreamElements / Fossabot 預設指令 → 預設關。
    {
        "command_name": "uptime",
        "category": "common",
        "cooldown": 10,
        "aliases": "開播時間",
        "enabled": False,
    },
    {
        "command_name": "ping",
        "category": "common",
        "cooldown": 5,
        "aliases": "alive",
        "custom_response": "Pong! @$(user)",
    },
    # ── 觀眾查詢（查自己；預設關閉：與 Nightbot / StreamElements / Fossabot /
    #    ChiwaBot 的同名指令衝突，交由實況主自行啟用）───────────────────────
    {
        "command_name": "followage",
        "category": "viewer",
        "cooldown": 15,
        "aliases": "追隨時間",
        "enabled": False,
    },
    {
        "command_name": "subage",
        "category": "viewer",
        "cooldown": 15,
        "aliases": "訂閱資訊",
        "enabled": False,
    },
    # rank 語意獨特（觀看時數＋留言活躍度，非點數排名）→ 預設開。
    {"command_name": "rank", "category": "viewer", "cooldown": 15, "aliases": "排名"},
    {
        "command_name": "bits",
        "category": "viewer",
        "cooldown": 15,
        "aliases": "小奇點",
        "enabled": False,
    },
    # ── 娛樂互動 ──────────────────────────────────────────────────────────────
    {"command_name": "fortune", "category": "fun", "cooldown": 5, "aliases": "運勢"},
    {"command_name": "tarot", "category": "fun", "cooldown": 5, "aliases": "塔羅"},
    {
        "command_name": "choose",
        "category": "fun",
        "cooldown": 5,
        "aliases": "選擇",
        "enabled": False,
    },
    {"command_name": "roll", "category": "fun", "cooldown": 5, "aliases": "輪盤"},
    # ── 遊戲工具（預設關閉，需手動啟用）──────────────────────────────────────
    {
        "command_name": "tft",
        "category": "game",
        "cooldown": 15,
        "aliases": "戰棋",
        "enabled": False,
    },
    {
        "command_name": "crosshairs",
        "category": "game",
        "cooldown": 5,
        "aliases": "準星",
        "enabled": False,
    },
    # ── 實況主工具（頻道營運資料，不是觀眾自助查詢）─────────────────────────
    {
        "command_name": "subcount",
        "category": "broadcaster",
        "min_role": "broadcaster",
        "cooldown": 30,
        "aliases": "訂閱數",
        "enabled": False,
    },
    # ── Mod 工具 ──────────────────────────────────────────────────────────────
    # so 常與其他 bot 衝突且用 bot 的 moderator token 執行 → 預設關 + Mod 限定。
    {
        "command_name": "so",
        "category": "moderator",
        "min_role": "moderator",
        "cooldown": 5,
        "aliases": "推薦",
        "enabled": False,
    },
    # condemn 會貼一整段頻道立場聲明 → 頻道管理表態，不是觀眾指令。
    {
        "command_name": "condemn",
        "category": "moderator",
        "min_role": "moderator",
        "cooldown": 5,
        "aliases": "斥責",
    },
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
    "checkin": "每日簽到並查詢該頻道累積天數",
    "help": "顯示觀眾可用的公開指令列表",
    "uptime": "查看目前已開播多久",
    "tft": "查詢聯盟戰棋排名",
    "fortune": "運勢占卜",
    "tarot": "每日塔羅（每個主題每天固定一張）",
    "condemn": "頻道反惡意言論聲明",
    "roll": "聊天室共用輪盤，中彈 timeout 60 秒",
    "choose": "從選項中隨機挑選一個",
    "rank": "查詢本月個人活躍度排名",
    "followage": "查詢自己追隨頻道多久",
    "subage": "查詢自己的累積訂閱月數與目前方案",
    "subcount": "供實況主查詢頻道訂閱總數",
    "bits": "查詢自己的小奇點排名與總額",
    "so": "Mod 指令：對指定頻道執行推薦 shoutout",
    "crosshairs": "顯示頻道準星收藏頁面連結",
}

# Intended operator of each builtin. This is separate from ``min_role``:
# audience classifies the job, while min_role is the channel's mutable execution
# gate. Public visibility requires both a viewer-facing audience and a viewer role.
BUILTIN_AUDIENCES: dict[str, str] = {
    "help": "viewer",
    "checkin": "viewer",
    "uptime": "viewer",
    "ping": "viewer",
    "followage": "viewer",
    "subage": "viewer",
    "rank": "viewer",
    "bits": "viewer",
    "fortune": "viewer",
    "tarot": "viewer",
    "choose": "viewer",
    "roll": "viewer",
    "tft": "viewer",
    "crosshairs": "viewer",
    "subcount": "broadcaster",
    "so": "moderator",
    "condemn": "moderator",
}

BUILTIN_USAGE: dict[str, str] = {
    "help": "!help",
    "checkin": "!checkin",
    "uptime": "!uptime",
    "ping": "!ping",
    "followage": "!followage",
    "subage": "!subage",
    "rank": "!rank",
    "bits": "!bits",
    "fortune": "!fortune",
    "tarot": "!tarot [綜合／感情／事業／財運]",
    "choose": "!choose <選項1> <選項2> …",
    "roll": "!roll",
    "tft": "!tft <玩家名稱>#<Tag>",
    "crosshairs": "!crosshairs",
    "subcount": "!subcount",
    "so": "!so <頻道名稱>",
    "condemn": "!condemn",
}

BUILTIN_DETAILS: dict[str, str] = {
    "help": "回覆此頻道的公開指令頁連結，讓觀眾查看目前已啟用且適合觀眾使用的指令。",
    "checkin": "為觸發者記錄當日簽到並回覆該頻道的累積簽到天數；同一天重複觸發不會重複累計。",
    "uptime": "查詢頻道目前是否正在直播；開播時回覆本場直播已持續的時間。",
    "ping": "回覆 Pong 與觸發者名稱，用來快速確認 Niibot 是否在線並能正常處理聊天室訊息。",
    "followage": "查詢觸發者是否追隨此頻道；已追隨時回覆從追隨日期至今的時間。",
    "subage": "查詢觸發者目前的訂閱狀態，並回覆累積訂閱月數、訂閱 Tier，以及是否為禮物訂閱。",
    "rank": "依本月觀看與聊天室活躍資料，回覆觸發者在此頻道的個人活躍度排名。",
    "bits": "查詢觸發者在此頻道累積投出的 Bits，並回覆其全期間排名與總額。",
    "fortune": "為觸發者產生一則當日運勢結果，適合一般聊天室娛樂互動。",
    "tarot": "抽取每日塔羅並依主題解讀；同一主題當天結果固定，可選綜合、感情、事業或財運。",
    "choose": "從觸發訊息提供的多個選項中隨機挑選一個，協助聊天室快速做決定。",
    "roll": "在聊天室參與者之間進行隨機輪盤；抽中者會被 timeout 60 秒。",
    "tft": "依玩家名稱與 Tag 查詢聯盟戰棋排名資料，並把結果回覆到聊天室。",
    "crosshairs": "回覆此頻道的公開準星收藏頁連結，讓觀眾瀏覽或複製準星設定。",
    "subcount": "使用實況主授權查詢頻道目前的訂閱者總數；這是營運統計，不列在觀眾公開指令頁。",
    "so": "由 Mod 對指定 Twitch 頻道執行 shoutout，並在聊天室顯示推薦資訊。",
    "condemn": "由 Mod 發送頻道預先定義的反惡意言論聲明，代表頻道管理立場。",
}

# Safe, illustrative chat examples for the dashboard. These strings are never
# executed and deliberately avoid depending on live Twitch or channel data.
BUILTIN_PREVIEWS: dict[str, dict[str, str]] = {
    "help": {
        "input": "!help",
        "output": "@小霓 公開指令列表：https://niibot.tv/streamer/commands",
    },
    "checkin": {
        "input": "!checkin",
        "output": "@小霓 今日簽到成功，已在這個頻道累積簽到 12 天！",
    },
    "uptime": {"input": "!uptime", "output": "目前已開播 2 小時 18 分鐘。"},
    "ping": {"input": "!ping", "output": "Pong! @小霓"},
    "followage": {
        "input": "!followage",
        "output": "@小霓 已追隨 1 年 3 個月 8 天。",
    },
    "subage": {
        "input": "!subage",
        "output": "@小霓 累積訂閱 14 個月，目前是 T2 訂閱者。",
    },
    "rank": {"input": "!rank", "output": "@小霓 本月活躍度排名第 8 名。"},
    "bits": {
        "input": "!bits",
        "output": "@小霓 累積贊助 1,250 Bits，目前排名第 6 名。",
    },
    "fortune": {"input": "!fortune", "output": "@小霓 今日運勢：大吉，幸運色是紫色。"},
    "tarot": {
        "input": "!tarot 感情",
        "output": "🃏 感情｜戀人（正位）｜解讀：坦率溝通會讓關係更靠近。",
    },
    "choose": {"input": "!choose 拉麵 壽司 咖哩", "output": "我選：壽司！"},
    "roll": {"input": "!roll", "output": "輪盤選中了 @阿澤，timeout 60 秒！"},
    "tft": {
        "input": "!tft Niibot#TW2",
        "output": "Niibot#TW2｜翡翠 II・42 LP｜台服單雙排名 #8,421",
    },
    "crosshairs": {
        "input": "!crosshairs",
        "output": "頻道準星收藏：https://niibot.tv/streamer/crosshairs",
    },
    "subcount": {"input": "!subcount", "output": "目前共有 128 位訂閱者，感謝大家的支持 💜"},
    "so": {
        "input": "!so streamer_name",
        "output": "快去看看 streamer_name 的頻道！https://twitch.tv/streamer_name",
    },
    "condemn": {
        "input": "!condemn",
        "output": "本頻道不接受仇恨、歧視或惡意攻擊言論，請共同維護聊天室環境。",
    },
}

# Public /commands page — includes usage examples

PUBLIC_DESCRIPTIONS: dict[str, str] = {
    "checkin": "每日簽到並查詢累積天數，用法：!簽到",
    "help": "顯示觀眾可用的公開指令列表",
    "uptime": "查看目前已開播多久",
    "ping": "確認 Niibot 是否在線",
    "tft": "查詢聯盟戰棋排名，用法：!tft <玩家名>#<tag>",
    "fortune": "運勢占卜",
    "tarot": "每日塔羅；同一主題當天結果固定。用法：!塔羅 [綜合/感情/事業/財運]",
    "roll": "誰是下一個？抽中禁言 60 秒，用法：!roll",
    "choose": "隨機選擇，用法：!choose 選項1 選項2 ...",
    "rank": "查詢本月個人活躍度排名",
    "followage": "查詢自己追隨頻道多久，用法：!followage",
    "subage": "查詢自己的累積訂閱月數與目前方案，用法：!subage",
    "bits": "查詢自己的小奇點排名與總額，用法：!bits",
    "crosshairs": "顯示頻道準星收藏頁面連結，用法：!crosshairs",
}
