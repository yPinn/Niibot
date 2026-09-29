"""Translation between Nightbot / StreamElements concepts and Niibot's.

Pure functions only — no I/O — so the parts most likely to silently corrupt a
user's commands are the parts that are cheapest to test.

Two rules run through everything here:

* **Permissions tighten, never loosen.** Where a source level has no Niibot
  equivalent we pick the stricter neighbour. Importing a command that fewer
  people can run is a nuisance; importing one that more people can run is a
  moderation incident.
* **Nothing is silently dropped.** Anything approximate lands in ``notes`` and
  anything untranslatable becomes an ``UNSUPPORTED`` row rather than vanishing.
"""

from __future__ import annotations

import re

from core.constants import MAX_RESPONSE_LENGTH
from shared.builtin_commands import BUILTIN_ALIAS_MAP, BUILTIN_MAP, COMMAND_RESERVED_NAMES
from shared.command_variables import unsupported_variables

from .models import (
    ImportFieldAction,
    ImportFieldOutcome,
    ImportItem,
    ImportSection,
    ImportStatus,
)

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

NIGHTBOT_ROLE_MAP: dict[str, str] = {
    "everyone": "everyone",
    "regular": "subscriber",  # a hand-picked trusted-viewer list; no equivalent → tighten
    "subscriber": "subscriber",
    "twitch_vip": "vip",
    "moderator": "moderator",
    "owner": "broadcaster",
}

# StreamElements levels, per its own !level documentation. 1500 (Broadcaster)
# is assignable from the dashboard only.
SE_ACCESS_LEVELS: list[tuple[int, str]] = [
    (100, "everyone"),
    (250, "subscriber"),
    (300, "subscriber"),  # "Regular" — no equivalent → tighten
    (400, "vip"),
    (500, "moderator"),
    (1000, "broadcaster"),  # "Super Moderator" — narrower than our moderator
    (1500, "broadcaster"),
]


def nightbot_role(user_level: str | None) -> tuple[str, list[str]]:
    """Map a Nightbot userLevel onto a Niibot min_role."""
    key = (user_level or "everyone").lower()
    role = NIGHTBOT_ROLE_MAP.get(key)
    if role is None:
        return "broadcaster", [f"不認得的權限「{user_level}」，保守設為實況主限定"]
    if key == "regular":
        return role, ["Nightbot 的 Regular 沒有對應層級，改設為訂閱者"]
    return role, []


def streamelements_role(access_level: int | None) -> tuple[str, list[str]]:
    """Map a StreamElements accessLevel onto a Niibot min_role."""
    level = access_level if access_level is not None else 100
    role = "broadcaster"
    for threshold, mapped in SE_ACCESS_LEVELS:
        if level <= threshold:
            role = mapped
            break
    notes: list[str] = []
    if level == 300:
        notes.append("StreamElements 的 Regular 沒有對應層級，改設為訂閱者")
    elif level == 1000:
        notes.append("StreamElements 的 Super Moderator 沒有對應層級，改設為實況主限定")
    return role, notes


# ---------------------------------------------------------------------------
# Builtin equivalents
# ---------------------------------------------------------------------------

# Deliberately source-specific and short. The platforms reuse names for
# different features, so a global name-only table can silently manufacture an
# equivalence that does not exist (for example StreamElements has no !winner
# default matching Nightbot's active-speaker picker).
BUILTIN_EQUIVALENTS_BY_SOURCE: dict[str, dict[str, str]] = {
    "nightbot": {
        "commands": "help",
        "game": "game",
        "marker": "marker",
        "tags": "tags",
        "title": "title",
        "winner": "winner",
    },
    "streamelements": {
        "accountage": "accountage",
        "commands": "help",
        "followage": "followage",
        "quote": "quote",
        "uptime": "uptime",
        "vanish": "del",
    },
}

_PLATFORM_LABELS = {"nightbot": "Nightbot", "streamelements": "StreamElements"}
_ROLE_ORDER = {"everyone": 0, "subscriber": 1, "vip": 2, "moderator": 3, "broadcaster": 4}

_SEMANTIC_REVIEW: dict[tuple[str, str], str] = {
    (
        "nightbot",
        "winner",
    ): "Nightbot 從近 10 分鐘有發言的人抽選；Niibot 改從目前 Twitch 在線名單抽選",
    (
        "nightbot",
        "commands",
    ): "Nightbot !commands 的新增、編輯與刪除子指令不會轉換；Niibot !help 只提供指令列表",
    (
        "streamelements",
        "followage",
    ): "StreamElements 可查指定使用者與其他頻道；Niibot 只查發話者在目前頻道的追隨時間",
    (
        "streamelements",
        "quote",
    ): "只會啟用 Niibot 的空白語錄庫；StreamElements 已有語錄資料不會匯入，指定編號與移除子指令也不同",
}


def builtin_equivalent(source_command: str, *, platform: str) -> str | None:
    """Return the source-specific Niibot builtin equivalent, if one exists."""
    source = platform.lower()
    return BUILTIN_EQUIVALENTS_BY_SOURCE.get(source, {}).get(source_command.lstrip("!").lower())


def default_command_item(
    command: str,
    *,
    key_prefix: str,
    platform: str,
    source_enabled: bool,
    source_role: str,
    source_cooldown: int | None,
    cooldown_provided: bool,
    role_notes: list[str] | None = None,
    cooldown_notes: list[str] | None = None,
) -> ImportItem:
    """Build the preview row for one of the source platform's default commands.

    Either it maps onto a Niibot builtin, or it is one of that platform's own
    features and gets listed as having no equivalent — never dropped, so the
    user can see what they are leaving behind.
    """
    source = platform.lower()
    platform_label = _PLATFORM_LABELS.get(source, platform)
    target = builtin_equivalent(command, platform=source)
    enabled_outcome = ImportFieldOutcome(
        field="enabled",
        action=ImportFieldAction.PRESERVED,
        detail=f"保留來源狀態：{'啟用' if source_enabled else '停用'}",
    )
    if target:
        definition = BUILTIN_MAP[target]
        catalog_role = str(definition.get("min_role", "everyone"))
        role = source_role
        outcomes = [enabled_outcome]
        notes = [f"改為 Niibot 內建的 !{target}"]

        if _ROLE_ORDER.get(role, 4) < _ROLE_ORDER[catalog_role]:
            role = catalog_role
            detail = f"來源為 {source_role}；Niibot 安全下限為 {catalog_role}，已收緊"
            if role_notes:
                detail = f"{detail}；{'；'.join(role_notes)}"
            outcomes.append(ImportFieldOutcome("min_role", ImportFieldAction.TIGHTENED, detail))
            notes.append(f"來源為 {source_role}；Niibot 安全下限為 {catalog_role}，已收緊")
            notes.extend(role_notes or [])
        elif role_notes:
            detail = "；".join(role_notes)
            outcomes.append(ImportFieldOutcome("min_role", ImportFieldAction.REVIEW, detail))
            notes.extend(role_notes)
        else:
            outcomes.append(
                ImportFieldOutcome(
                    "min_role",
                    ImportFieldAction.PRESERVED,
                    f"保留最低身分：{role}",
                )
            )

        if cooldown_provided:
            cooldown = source_cooldown if source_cooldown is not None else 0
            if cooldown_notes:
                detail = "；".join(cooldown_notes)
                outcomes.append(ImportFieldOutcome("cooldown", ImportFieldAction.REVIEW, detail))
                notes.extend(cooldown_notes)
            else:
                outcomes.append(
                    ImportFieldOutcome(
                        "cooldown",
                        ImportFieldAction.PRESERVED,
                        f"保留冷卻：{cooldown} 秒",
                    )
                )
        else:
            cooldown = int(definition.get("cooldown", 0))
            detail = f"來源未提供冷卻設定，沿用 Niibot 預設 {cooldown} 秒"
            outcomes.append(ImportFieldOutcome("cooldown", ImportFieldAction.REVIEW, detail))
            notes.append(detail)

        semantic_note = _SEMANTIC_REVIEW.get((source, command))
        if semantic_note:
            outcomes.append(
                ImportFieldOutcome("semantics", ImportFieldAction.REVIEW, semantic_note)
            )
            notes.append(semantic_note)

        # If the old trigger remains a catalog alias (e.g. !vanish → !del),
        # users can keep typing it. Otherwise make the renamed trigger explicit.
        if command != target and BUILTIN_ALIAS_MAP.get(command) != target:
            detail = f"觸發名稱由 !{command} 改為 !{target}"
            outcomes.append(ImportFieldOutcome("command_name", ImportFieldAction.REVIEW, detail))
            notes.append(detail)

        needs_review = any(
            outcome.action is not ImportFieldAction.PRESERVED for outcome in outcomes
        )
        return ImportItem(
            key=f"{key_prefix}:default:{command}",
            section=ImportSection.BUILTIN,
            status=ImportStatus.REVIEW if needs_review else ImportStatus.OK,
            source_name=f"!{command}",
            source_enabled=source_enabled,
            notes=notes,
            field_outcomes=outcomes,
            cooldown=cooldown,
            min_role=role,
            builtin_target=target,
        )
    return ImportItem(
        key=f"{key_prefix}:default:{command}",
        section=ImportSection.UNSUPPORTED,
        status=ImportStatus.UNSUPPORTED,
        source_name=f"!{command}",
        source_enabled=source_enabled,
        notes=[f"這是 {platform_label} 的平台功能，Niibot 沒有對應的指令"],
        field_outcomes=[
            enabled_outcome,
            ImportFieldOutcome(
                "semantics",
                ImportFieldAction.DROPPED,
                f"{platform_label} 平台功能無法在 Niibot 執行",
            ),
        ],
    )


def check_length(response: str) -> list[str]:
    """Blockers for a response too long to survive variable expansion.

    Both source platforms allow up to 500 characters, more than our own cap, so
    the importer has to enforce it too — the dashboard's Pydantic constraint
    never sees these rows.
    """
    if len(response) <= MAX_RESPONSE_LENGTH:
        return []
    return [f"回應有 {len(response)} 字，超過 Niibot 的 {MAX_RESPONSE_LENGTH} 字上限"]


def classify(
    notes: list[str], blockers: list[str], conflict: str | None
) -> tuple[ImportStatus, ImportSection, list[str]]:
    """Decide a row's status and section, and fold the reason into its notes.

    Precedence is deliberate: something Niibot cannot do at all outranks a name
    clash, which outranks an approximate translation.
    """
    if blockers:
        return ImportStatus.UNSUPPORTED, ImportSection.UNSUPPORTED, [*notes, *blockers]
    if conflict:
        return (
            ImportStatus.CONFLICT,
            ImportSection.CUSTOM,
            [*notes, f"已經有 !{conflict} 了，預設跳過"],
        )
    if notes:
        return ImportStatus.REVIEW, ImportSection.CUSTOM, notes
    return ImportStatus.OK, ImportSection.CUSTOM, notes


# ---------------------------------------------------------------------------
# Command names
# ---------------------------------------------------------------------------

_NAME_STRIP = re.compile(r"[^\w一-鿿-]", re.UNICODE)


def normalize_command_name(raw: str) -> str:
    """Turn a source trigger into a Niibot command_name (no prefix, lowercase)."""
    return _NAME_STRIP.sub("", raw.strip().lstrip("!").lower())


def find_conflict(name: str, existing: set[str]) -> str | None:
    """Return the thing *name* collides with, or None.

    Checks the channel's existing command names and aliases plus the builtin
    catalog. A name we have no builtin for is simply not a conflict — the
    import does not require us to own the other platform's commands.
    """
    key = name.lower()
    if key in existing:
        return key
    if key in BUILTIN_MAP:
        return key
    if key in BUILTIN_ALIAS_MAP:
        return BUILTIN_ALIAS_MAP[key]
    if key in COMMAND_RESERVED_NAMES:
        return key
    return None


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

# StreamElements writes both ${foo} and $(foo); the rules below accept either.
_SE_RULES: list[tuple[re.Pattern[str], str]] = [
    # Collapse whole-query URL wrappers onto Niibot's canonical variables.
    # These must run before argument ranges are normalised.
    (
        re.compile(
            r"\$[({]\s*(?:queryescape|queryencode)\s+"
            r"\$[({]\s*1\s*:\s*[)}]\s*[)}]"
        ),
        "$(queryescape)",
    ),
    (
        re.compile(
            r"\$[({]\s*(?:pathescape|pathencode)\s+"
            r"\$[({]\s*1\s*:\s*[)}]\s*[)}]"
        ),
        "$(pathescape)",
    ),
    # First argument with caller fallback is exactly Niibot's $(touser).
    (
        re.compile(
            r"\$[({]\s*1\s*\|\s*"
            r"\$[({]\s*(?:user|sender|source)(?:\.name)?\s*[)}]\s*[)}]"
        ),
        "$(touser)",
    ),
    # ${random.pick a,b,c} → $(pick a,b,c)
    (re.compile(r"\$[({]\s*random\.pick\s+([^)}]+)[)}]"), r"$(pick \1)"),
    # ${random.1-100} → $(random 1,100)
    (re.compile(r"\$[({]\s*random\.(\d+)-(\d+)\s*[)}]"), r"$(random \1,\2)"),
    # StreamElements' sender/source is always the caller. Its bare user defaults
    # to the first argument, which is closest to Niibot's $(touser).
    (re.compile(r"\$[({]\s*user(?:\.name)?\s*[)}]"), "$(touser)"),
    # Run caller aliases after user so the canonical $(user) output is not
    # interpreted again as a StreamElements user token.
    (re.compile(r"\$[({]\s*(?:sender|source)(?:\.name)?\s*[)}]"), "$(user)"),
    (re.compile(r"\$[({]\s*touser\s*[)}]"), "$(touser)"),
    (re.compile(r"\$[({]\s*channel\s*[)}]"), "$(channel)"),
    (re.compile(r"\$[({]\s*count\s*[)}]"), "$(count)"),
    # Preserve argument ranges and defaults in the canonical spelling.
    (
        re.compile(r"\$[({]\s*([1-9]\d*)\s*:\s*([1-9]\d*)\s*[)}]"),
        r"$(\1:\2)",
    ),
    (re.compile(r"\$[({]\s*([1-9]\d*)\s*:\s*[)}]"), r"$(\1:)"),
    (
        re.compile(r"\$[({]\s*([1-9]\d*)\s*\|\s*([^(){}]*)[)}]"),
        r"$(\1|\2)",
    ),
    (re.compile(r"\$[({]\s*([1-9]\d*)\s*[)}]"), r"$(\1)"),
]

# Nightbot's syntax is already $(...), so only the outliers need rewriting.
_NIGHTBOT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\$\(\s*querystring\s*\)"), "$(queryescape)"),
    (re.compile(r"\$\(\s*arguments\s*\)"), "$(query)"),
]

# Explanations for the variables users hit most often, so the preview says why
# rather than just refusing.
_UNSUPPORTED_REASONS: dict[str, str] = {
    "eval": "用到 $(eval) 執行 JavaScript，Niibot 不支援",
    "urlfetch": "用到 $(urlfetch) 對外抓取資料，Niibot 不支援",
    "customapi": "用到 $(customapi) 對外抓取資料，Niibot 不支援",
    "count": "用到具名計數器，Niibot 只有每個指令自己的 $(count)",
    "getcount": "用到具名計數器，Niibot 只有每個指令自己的 $(count)",
    "setgame": "會改動頻道遊戲分類，Niibot 不支援",
    "settitle": "會改動頻道標題，Niibot 不支援",
    "game": "讀取頻道遊戲分類，Niibot 不支援",
    "title": "讀取頻道標題，Niibot 不支援",
    "uptime": "讀取開播時間，請改用內建的 !uptime",
    "twitch": "讀取他人 Twitch 資料，Niibot 不支援",
    "weather": "讀取天氣資料，Niibot 不支援",
    "countdown": "倒數計時，Niibot 不支援",
    "countup": "計時，Niibot 不支援",
    "math": "數學運算，Niibot 不支援",
    "repeat": "重複字串，Niibot 不支援",
    "time": "讀取時間或倒數，Niibot 不支援",
    # Reached only via the root split — plain $(user) / $(channel) are stripped
    # as valid forms before leftovers are collected, so these catch the
    # attribute spellings such as ${user.lastseen} and ${channel.subs}.
    "user": "讀取觀眾的歷史紀錄，Niibot 不支援",
    "channel": "讀取頻道統計資料，Niibot 不支援",
}


def _explain(head: str) -> str:
    if head == ":":
        return "用到包含指令名稱的參數範圍 $(:N)，Niibot 的參數只從使用者輸入開始"
    if head.isdigit():
        return "用到 Niibot 不支援的參數條件或格式"
    if head in _UNSUPPORTED_REASONS:
        return _UNSUPPORTED_REASONS[head]
    root = head.split(".", 1)[0]
    if root in _UNSUPPORTED_REASONS:
        return _UNSUPPORTED_REASONS[root]
    return f"用到 Niibot 不支援的變數 ${{{head}}}"


def translate_variables(text: str, source: str) -> tuple[str, list[str], list[str]]:
    """Rewrite a source response into Niibot's variable syntax.

    Returns ``(translated, notes, blockers)``. ``blockers`` is non-empty when
    the response relies on something Niibot cannot do, which makes the item
    unsupported rather than merely approximate.
    """
    rules = (
        _SE_RULES if source == "streamelements" else _NIGHTBOT_RULES if source == "nightbot" else []
    )
    translated = text or ""
    for pattern, replacement in rules:
        translated = pattern.sub(replacement, translated)

    notes: list[str] = []
    if translated != (text or ""):
        notes.append("變數語法已改寫為 Niibot 格式")

    # The supported grammar lives in shared.command_variables so this can never
    # fall behind what the bot actually expands.
    blockers = [_explain(head) for head in unsupported_variables(translated)]
    return translated, notes, blockers
