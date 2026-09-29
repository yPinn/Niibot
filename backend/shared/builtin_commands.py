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

`"enabled": False` — default a command OFF when another bot commonly owns the
same name, when it needs channel-specific setup, or when it performs a
moderation / Twitch write action. Safe Niibot-original reads and interactions
stay on.

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
    "channel": "頻道資訊",
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
    # schedule 是 Niibot 原創功能，沒有其他 bot 的同名指令衝突 → 預設開。
    {
        "command_name": "schedule",
        "category": "common",
        "cooldown": 10,
        "aliases": "下次開台,排程",
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
    # del 撞 StreamElements 的 !vanish 預設指令 → 預設關。永遠 everyone（對自己
    # 動手，不需要額外權限判斷）。test_new_parity_builtins_land_in_their_declared_category
    # 鎖定 del 緊接在 ping 後面，新增項目不要插進這兩個中間。
    {
        "command_name": "del",
        "category": "common",
        "cooldown": 5,
        "aliases": "刪,vanish",
        "enabled": False,
    },
    # ── 觀眾查詢（查自己；預設關閉：與 Nightbot / StreamElements / Fossabot /
    #    ChiwaBot 的同名指令衝突，交由實況主自行啟用）───────────────────────
    # rank 讀取每日簽到 ledger 的累積天數排名，與後台簽到排行榜同一套排序 → 預設開。
    {"command_name": "rank", "category": "viewer", "cooldown": 15, "aliases": "排名"},
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
    {
        "command_name": "accountage",
        "category": "viewer",
        "cooldown": 15,
        "aliases": "帳號年齡",
        "enabled": False,
    },
    {
        "command_name": "bits",
        "category": "viewer",
        "cooldown": 15,
        "aliases": "小奇點",
        "enabled": False,
    },
    # quote 撞 Nightbot 預設指令模板 → 預設關。查詢對所有人開放（min_role 維持
    # everyone），新增／刪除需要 Mod 以上——handler 內用 has_role() 另外判斷。
    {
        "command_name": "quote",
        "category": "viewer",
        "cooldown": 5,
        "aliases": "語錄",
        "enabled": False,
    },
    # ── 娛樂互動 ──────────────────────────────────────────────────────────────
    {
        "command_name": "choose",
        "category": "fun",
        "cooldown": 5,
        "aliases": "選",
    },
    {"command_name": "fortune", "category": "fun", "cooldown": 5, "aliases": "運勢"},
    {"command_name": "tarot", "category": "fun", "cooldown": 5, "aliases": "塔羅"},
    # roll 會讓觸發者有機率被 timeout，需由頻道明確選用。
    {
        "command_name": "roll",
        "category": "fun",
        "cooldown": 5,
        "aliases": "輪盤",
        "enabled": False,
    },
    # ── 遊戲工具（預設關閉，需手動啟用）──────────────────────────────────────
    {
        "command_name": "crosshairs",
        "category": "game",
        "cooldown": 5,
        "aliases": "xhc,準星",
        "enabled": False,
    },
    {
        "command_name": "tft",
        "category": "game",
        "cooldown": 15,
        "aliases": "戰棋",
        "enabled": False,
    },
    # ── 頻道資訊（所有人可查詢，修改仍由 handler 限制為 Mod 以上）───────────
    # title/game/tags 撞 Nightbot / StreamElements 預設指令模板 → 預設關。查詢對
    # 所有人開放（min_role 維持 everyone），修改需要 Mod 以上——check_command 只有
    # 單一 min_role 閘門，這個「查詢／修改」分權是 handler 內用 has_role() 另外判斷。
    {
        "command_name": "title",
        "category": "channel",
        "cooldown": 10,
        "aliases": "標題",
        "enabled": False,
    },
    {
        "command_name": "game",
        "category": "channel",
        "cooldown": 10,
        "aliases": "分類",
        "enabled": False,
    },
    {
        "command_name": "tags",
        "category": "channel",
        "cooldown": 10,
        "aliases": "標籤",
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
    # marker 撞 Nightbot 預設指令模板 → 預設關。沒有查詢面，永遠 Mod 限定。
    {
        "command_name": "marker",
        "category": "moderator",
        "min_role": "moderator",
        "cooldown": 10,
        "aliases": "標記",
        "enabled": False,
    },
    # winner 撞 Nightbot 預設指令模板 → 預設關。沒有查詢面，永遠 Mod 限定。
    {
        "command_name": "winner",
        "category": "moderator",
        "min_role": "moderator",
        "cooldown": 10,
        "aliases": "抽",
        "enabled": False,
    },
    # condemn 會代表頻道貼出管理立場，需由頻道明確選用。
    {
        "command_name": "condemn",
        "category": "moderator",
        "min_role": "moderator",
        "cooldown": 5,
        "aliases": "斥責",
        "enabled": False,
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

# Top-level TwitchIO commands that are intentionally outside the channel
# configurable builtin catalog.  Custom commands and imports must not claim
# these names because the custom router runs before TwitchIO dispatch and would
# otherwise shadow operational commands.
RUNTIME_ONLY_COMMAND_NAMES: frozenset[str] = frozenset(
    {
        "ai",
        "問",
        "ovltest",
        "cmd",
        "gq",
        "comp",
        "np",
        "影片",
        "vq",
    }
)

# External bots use !commands for their command-list builtin.  Niibot converts
# that default to !help, so the source name stays reserved even though it is not
# a live TwitchIO alias (running two command-list implementations is ambiguous).
IMPORT_COMPAT_RESERVED_NAMES: frozenset[str] = frozenset({"commands"})

# One namespace shared by the catalog, custom-command creation and import
# conflict detection.  Values are normalised to lowercase where applicable;
# CJK aliases are unaffected by lower().
COMMAND_RESERVED_NAMES: frozenset[str] = frozenset(
    {name.lower() for name in BUILTIN_NAMES}
    | {alias.lower() for alias in BUILTIN_ALIAS_MAP}
    | {name.lower() for name in RUNTIME_ONLY_COMMAND_NAMES}
    | {name.lower() for name in IMPORT_COMPAT_RESERVED_NAMES}
)

COMMAND_RESERVED_OWNERS: dict[str, str] = {
    **{name.lower(): name for name in BUILTIN_NAMES},
    **{alias.lower(): owner for alias, owner in BUILTIN_ALIAS_MAP.items()},
    **{name.lower(): name.lower() for name in RUNTIME_ONLY_COMMAND_NAMES},
    **{name.lower(): name.lower() for name in IMPORT_COMPAT_RESERVED_NAMES},
}

# ── Descriptions (used by the API service layer) ──────────────────────────────

BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "help": "查看可用的公開指令",
    "checkin": "每日簽到並查看累積天數",
    "schedule": "查看今天或下次的開台排程",
    "uptime": "查看目前已開播多久",
    "ping": "確認 Niibot 是否在線",
    "del": "清除自己最近的聊天室留言",
    "rank": "查看累積簽到排名",
    "followage": "查看自己追隨頻道多久",
    "subage": "查看累積訂閱月數與目前方案",
    "accountage": "查看 Twitch 帳號建立時間",
    "bits": "查看小奇點排名與累積總額",
    "quote": "查看頻道語錄",
    "choose": "從多個選項中隨機挑選一個",
    "fortune": "查看今日運勢",
    "tarot": "查看每日塔羅",
    "roll": "觸發者有機率 timeout 60 秒",
    "crosshairs": "查看頻道準星收藏",
    "tft": "查看聯盟戰棋排名",
    "title": "查看或修改頻道標題",
    "game": "查看或修改頻道分類",
    "tags": "查看或修改頻道標籤",
    "subcount": "查看頻道訂閱總數",
    "so": "推薦指定頻道",
    "marker": "標記目前直播時間點",
    "winner": "隨機抽出一位在線觀眾",
    "condemn": "發送頻道反惡意言論聲明",
}

# Intended operator of each builtin. This is separate from ``min_role``:
# audience classifies the job, while min_role is the channel's mutable execution
# gate. Public visibility requires both a viewer-facing audience and a viewer role.
BUILTIN_AUDIENCES: dict[str, str] = {
    "help": "viewer",
    "checkin": "viewer",
    "uptime": "viewer",
    "schedule": "viewer",
    "ping": "viewer",
    "del": "viewer",
    "followage": "viewer",
    "subage": "viewer",
    "rank": "viewer",
    "bits": "viewer",
    "accountage": "viewer",
    "quote": "viewer",
    "fortune": "viewer",
    "tarot": "viewer",
    "choose": "viewer",
    "roll": "viewer",
    "tft": "viewer",
    "crosshairs": "viewer",
    "subcount": "broadcaster",
    "title": "viewer",
    "game": "viewer",
    "tags": "viewer",
    "so": "moderator",
    "condemn": "moderator",
    "marker": "moderator",
    "winner": "moderator",
}

BUILTIN_USAGE: dict[str, str] = {
    "help": "!help",
    "checkin": "!checkin",
    "uptime": "!uptime",
    "schedule": "!schedule ｜ !下次開台 ｜ !排程",
    "ping": "!ping",
    "del": "!del",
    "followage": "!followage",
    "subage": "!subage",
    "rank": "!rank",
    "bits": "!bits",
    "accountage": "!accountage [使用者]",
    "quote": "!quote [編號] ｜ !quote add <內容> ｜ !quote del <編號>",
    "fortune": "!fortune",
    "tarot": "!tarot [綜合／感情／事業／財運]",
    "choose": "!choose <選項1> <選項2> …",
    "roll": "!roll",
    "tft": "!tft <玩家名稱>#<Tag>",
    "crosshairs": "!crosshairs",
    "subcount": "!subcount",
    "title": "!title [新標題]",
    "game": "!game [分類名稱]",
    "tags": "!tags [標籤1,標籤2,…]",
    "so": "!so <頻道名稱>",
    "condemn": "!condemn",
    "marker": "!marker [描述]",
    "winner": "!winner",
}

BUILTIN_DETAILS: dict[str, str] = {
    "help": "回覆此頻道的公開指令頁。",
    "checkin": "記錄當日簽到並回覆累積天數；同一天不重複計算。",
    "schedule": "回覆今天或未來一週最近一次排程。",
    "uptime": "回覆目前直播狀態與本場開播時間。",
    "ping": "回覆 Pong 與觸發者名稱。",
    "del": "將自己 timeout 1 秒以清除最近留言；Niibot 需為 Mod。",
    "rank": "回覆自己的累積簽到名次。",
    "followage": "回覆自己追隨此頻道的時間。",
    "subage": "回覆累積訂閱月數、方案與禮物訂閱狀態。",
    "accountage": "回覆自己或指定使用者的帳號建立日期與帳齡。",
    "bits": "回覆自己的小奇點排名與累積總額。",
    "quote": "隨機或依編號查看語錄；Mod 以上可新增與刪除。",
    "choose": "從輸入的選項中隨機回覆一個。",
    "fortune": "產生一則今日運勢。",
    "tarot": "依主題解讀每日塔羅；同一主題當天結果固定。",
    "roll": "觸發者有機率被 timeout 60 秒；Niibot 需為 Mod。",
    "crosshairs": "回覆此頻道的公開準星收藏頁。",
    "tft": "依玩家名稱與 Tag 回覆聯盟戰棋排名。",
    "title": "不帶參數查看標題；Mod 以上可帶參數修改。",
    "game": "不帶參數查看分類；Mod 以上可帶參數修改。",
    "tags": "不帶參數查看標籤；Mod 以上可帶參數修改，最多 10 個。",
    "subcount": "回覆目前訂閱總數；僅供實況主使用。",
    "so": "推薦指定 Twitch 頻道；Niibot 需為 Mod。",
    "marker": "在目前直播建立時間標記；需直播中並開啟 VOD。",
    "winner": "從目前在線觀眾中隨機抽出一人；Niibot 需為 Mod。",
    "condemn": "發送頻道預設的反惡意言論聲明。",
}


def _integration(
    kind: str,
    label: str,
    *,
    capability_key: str | None = None,
    mode: str = "all",
    requires_bot_moderator: bool = False,
    conditions: tuple[str, ...] = (),
) -> dict:
    requirements = []
    if capability_key:
        requirements.append(
            {
                "capability_key": capability_key,
                "mode": mode,
                "requires_bot_moderator": requires_bot_moderator,
            }
        )
    return {
        "kind": kind,
        "label": label,
        "requirements": requirements,
        "conditions": list(conditions),
    }


# External dependency contract consumed by the Commands API/UI.  Core chat
# grants (`bot_chat` + `broadcaster_chat`) are page-wide runtime prerequisites;
# this table lists only each command's additional dependency.
BUILTIN_INTEGRATIONS: dict[str, dict] = {
    "help": _integration("internal", "Niibot 指令頁"),
    "checkin": _integration("internal", "Niibot 簽到資料"),
    "uptime": _integration("twitch_public", "Twitch 直播狀態"),
    "ping": _integration("internal", "Niibot 聊天回覆"),
    "del": _integration(
        "twitch_capability",
        "Twitch 自我逾時",
        capability_key="banned_users",
        requires_bot_moderator=True,
        conditions=("Bot 必須是頻道 Mod",),
    ),
    "schedule": _integration("internal", "Niibot 排程資料"),
    "followage": _integration(
        "twitch_capability",
        "Twitch 追隨資料",
        capability_key="followers",
        requires_bot_moderator=True,
        conditions=("Bot 必須是頻道 Mod",),
    ),
    "subage": _integration(
        "twitch_capability",
        "Twitch 訂閱資料",
        capability_key="subscriptions",
    ),
    "rank": _integration("internal", "Niibot 簽到資料"),
    "bits": _integration(
        "twitch_capability",
        "Twitch Bits 資料",
        capability_key="cheers",
    ),
    "accountage": _integration("twitch_public", "Twitch 帳號資料"),
    "quote": _integration("internal", "Niibot 語錄資料"),
    "fortune": _integration("internal", "Niibot 運勢資料"),
    "tarot": _integration("internal", "Niibot 塔羅資料"),
    "choose": _integration("internal", "Niibot 隨機選擇"),
    "roll": _integration(
        "twitch_capability",
        "Twitch 逾時效果",
        capability_key="banned_users",
        mode="effect",
        requires_bot_moderator=True,
        conditions=("缺少權限時仍會公布結果，但不會執行逾時", "Bot 必須是頻道 Mod"),
    ),
    "tft": _integration("external_service", "TFT 排名服務"),
    "crosshairs": _integration("internal", "Niibot 準星資料"),
    "title": _integration(
        "twitch_capability",
        "Twitch 頻道標題",
        capability_key="channel_info",
        mode="write",
        conditions=("查詢不需額外 user scope；修改需 Mod 以上",),
    ),
    "game": _integration(
        "twitch_capability",
        "Twitch 頻道分類",
        capability_key="channel_info",
        mode="write",
        conditions=("查詢不需額外 user scope；修改需 Mod 以上",),
    ),
    "tags": _integration(
        "twitch_capability",
        "Twitch 頻道標籤",
        capability_key="channel_info",
        mode="write",
        conditions=("查詢不需額外 user scope；修改需 Mod 以上",),
    ),
    "subcount": _integration(
        "twitch_capability",
        "Twitch 訂閱總數",
        capability_key="subscriptions",
    ),
    "so": _integration(
        "twitch_capability",
        "Twitch Shoutout",
        capability_key="shoutouts",
        requires_bot_moderator=True,
        conditions=("Bot 必須是頻道 Mod", "頻道需直播中且有觀眾", "受 Twitch Shoutout 限流"),
    ),
    "condemn": _integration("internal", "Niibot 聊天回覆"),
    "marker": _integration(
        "twitch_capability",
        "Twitch 直播標記",
        capability_key="channel_info",
        conditions=("頻道必須直播中", "必須開啟 VOD", "rerun／premiere 無法建立標記"),
    ),
    "winner": _integration(
        "twitch_capability",
        "Twitch 聊天室名單",
        capability_key="chatters",
        requires_bot_moderator=True,
        conditions=("Bot 必須是頻道 Mod", "目前只取前 1,000 位在線 chatters"),
    ),
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
    "schedule": {
        "input": "!schedule",
        "output": "今天 20:00 開始，週一固定台，預計玩 Just Chatting",
    },
    "ping": {"input": "!ping", "output": "Pong! @小霓"},
    "del": {"input": "!del", "output": "（觸發者最近的留言被清除，無聊天室回覆）"},
    "followage": {
        "input": "!followage",
        "output": "@小霓 已追隨 1 年 3 個月 8 天。",
    },
    "subage": {
        "input": "!subage",
        "output": "@小霓 累積訂閱 14 個月，目前是 T2 訂閱者。",
    },
    "rank": {"input": "!rank", "output": "@小霓 在 132 人中排到【第 8 名】，累積簽到 12 天！"},
    "bits": {
        "input": "!bits",
        "output": "@小霓 累積贊助 1,250 Bits，目前排名第 6 名。",
    },
    "accountage": {
        "input": "!accountage",
        "output": "@小霓 的 Twitch 帳號已建立 3 年 2 個月 10 天（2023-07-05）",
    },
    "quote": {"input": "!quote", "output": "#3：這波不虧"},
    "fortune": {"input": "!fortune", "output": "@小霓 今日運勢：大吉，幸運色是紫色。"},
    "tarot": {
        "input": "!tarot 感情",
        "output": "🃏 感情｜戀人（正位）｜解讀：坦率溝通會讓關係更靠近。",
    },
    "choose": {"input": "!choose 拉麵 壽司 咖哩", "output": "我選：壽司！"},
    "roll": {"input": "!roll", "output": "@小霓 被狼人選中，timeout 60 秒！"},
    "tft": {
        "input": "!tft Niibot#TW2",
        "output": "Niibot#TW2｜翡翠 II・42 LP｜台服單雙排名 #8,421",
    },
    "crosshairs": {
        "input": "!crosshairs",
        "output": "頻道準星收藏：https://niibot.tv/streamer/crosshairs",
    },
    "subcount": {"input": "!subcount", "output": "目前共有 128 位訂閱者，感謝大家的支持 💜"},
    "title": {"input": "!title", "output": "目前標題：晚安！今天來聊聊新版本的改動"},
    "game": {"input": "!game", "output": "目前分類：Just Chatting"},
    "tags": {"input": "!tags", "output": "目前標籤：中文、聊天、New"},
    "so": {
        "input": "!so streamer_name",
        "output": "快去看看 streamer_name 的頻道！https://twitch.tv/streamer_name",
    },
    "condemn": {
        "input": "!condemn",
        "output": "本頻道不接受仇恨、歧視或惡意攻擊言論，請共同維護聊天室環境。",
    },
    "marker": {"input": "!marker 精彩片段", "output": "已建立標記（12:34）"},
    "winner": {"input": "!winner", "output": "🎉 恭喜 @阿澤 中獎了！"},
}

# Public /commands page — includes usage examples

PUBLIC_DESCRIPTIONS: dict[str, str] = {
    "help": "查看可用的公開指令",
    "checkin": "每日簽到並查看累積天數",
    "schedule": "查看今天或下次的開台排程",
    "uptime": "查看目前已開播多久",
    "ping": "確認 Niibot 是否在線",
    "del": "清除自己最近的聊天室留言",
    "rank": "查看累積簽到排名",
    "followage": "查看自己追隨頻道多久",
    "subage": "查看累積訂閱月數與目前方案",
    "accountage": "查看 Twitch 帳號建立時間；用法：!accountage [使用者]",
    "bits": "查看小奇點排名與累積總額",
    "quote": "查看頻道語錄；Mod 以上可新增或刪除",
    "choose": "從多個選項中隨機挑選一個；用法：!choose <選項1> <選項2> …",
    "fortune": "查看今日運勢",
    "tarot": "查看每日塔羅；用法：!tarot [綜合／感情／事業／財運]",
    "roll": "觸發者有機率 timeout 60 秒",
    "crosshairs": "查看頻道準星收藏",
    "tft": "查看聯盟戰棋排名；用法：!tft <玩家名稱>#<Tag>",
    "title": "查看頻道標題；Mod 以上可帶參數修改",
    "game": "查看頻道分類；Mod 以上可帶參數修改",
    "tags": "查看頻道標籤；Mod 以上可帶參數修改",
}
