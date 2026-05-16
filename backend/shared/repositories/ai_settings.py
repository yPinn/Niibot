"""Repository for per-channel AI character settings."""

from __future__ import annotations

import asyncpg

from shared.cache import AsyncTTLCache, cached

_ai_settings_cache = AsyncTTLCache(maxsize=64, ttl=300)

# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_AI_SETTINGS: dict = {
    "bot_name": "Twitch 聊天室機器人",
    "persona": "",
    "response_lang": "zh-tw",
    "refusal_style": "humorous",
    "max_tokens": 250,
    "enabled_emotes": [],
}

_LANG_TEXT: dict[str, str] = {
    "zh-tw": "繁體中文（除非使用者明確要求其他語言）",
    "en": "英文（除非使用者明確要求其他語言）",
    "auto": "配合使用者語言",
}

_REFUSAL_TEXT: dict[str, str] = {
    "humorous": (
        "遇此類請求請用冷幽默方式婉拒"
        "（例如假裝系統錯誤、自稱腦袋當機、或用無辜語氣說做不到），"
        "不要直接說「我無法回答」"
    ),
    "polite": "遇此類請求請禮貌說無法協助，不必解釋原因",
}


def build_system_prompt(settings: dict) -> str:
    """Assemble a system prompt string from structured settings fields."""
    name = (settings.get("bot_name") or "Twitch 聊天室機器人").strip()
    persona = (settings.get("persona") or "").strip()
    lang = _LANG_TEXT.get(settings.get("response_lang", "zh-tw"), _LANG_TEXT["zh-tw"])
    refusal = _REFUSAL_TEXT.get(
        settings.get("refusal_style", "humorous"), _REFUSAL_TEXT["humorous"]
    )
    emotes: list[str] = settings.get("enabled_emotes") or []

    parts: list[str] = [
        f"你是 {name}，回應直接顯示於公開直播聊天室，須符合 Twitch 服務條款。",
    ]

    if persona:
        parts.append(f"\n\n個性：{persona}")

    parts.append(
        "\n\n格式：\n"
        f"- 語言：{lang}\n"
        "- 長度：最多100字，1-2句完整句子\n"
        "- 一段連貫文字，禁止換行，禁止 Markdown 符號（**、*、#、_、- 等）\n"
        "- 直接回答，不輸出思考過程\n"
        "- 人名、地名等專有名詞請附上英文原名或優先使用英文（例：Copernicus、Newton），"
        "避免中文字元組合意外觸發平台自動過濾器"
    )

    if emotes:
        parts.append(
            f"\n\n貼圖：可在回覆中自然地插入以下 Twitch 貼圖名稱（直接輸入名稱即可，Twitch 自動渲染）："
            f"{' '.join(emotes)}"
        )

    parts.append(
        "\n\n平台限制：禁止生成仇恨攻擊、性相關、或針對特定人的騷擾威脅等內容；"
        f"{refusal}。知識、遊戲、娛樂等一般問題請正常回答。"
    )

    return "".join(parts)


# ── Repository ───────────────────────────────────────────────────────────────


class AISettingsRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @cached(
        cache=_ai_settings_cache,
        key_func=lambda self, channel_id: f"ai_settings:{channel_id}",
    )
    async def get(self, channel_id: str) -> dict:
        """Return ai_settings row for channel, or defaults if none exists."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT bot_name, persona, response_lang, refusal_style, max_tokens, enabled_emotes "
                "FROM ai_settings WHERE channel_id = $1",
                channel_id,
            )
        if not row:
            return dict(DEFAULT_AI_SETTINGS)
        d = dict(row)
        d["enabled_emotes"] = list(d.get("enabled_emotes") or [])
        return d

    async def upsert(self, channel_id: str, **fields) -> dict:
        """Insert or update settings for a channel. Invalidates cache.

        Only the provided keyword arguments are applied; unrecognised keys
        are silently ignored to avoid SQL injection via column names.
        """
        allowed = {
            "bot_name",
            "persona",
            "response_lang",
            "refusal_style",
            "max_tokens",
            "enabled_emotes",
        }
        data = {k: v for k, v in fields.items() if k in allowed}

        current = await self.get(channel_id)
        merged = {**current, **data}

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ai_settings
                    (channel_id, bot_name, persona, response_lang, refusal_style, max_tokens, enabled_emotes, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, now())
                ON CONFLICT (channel_id) DO UPDATE SET
                    bot_name      = EXCLUDED.bot_name,
                    persona       = EXCLUDED.persona,
                    response_lang = EXCLUDED.response_lang,
                    refusal_style = EXCLUDED.refusal_style,
                    max_tokens    = EXCLUDED.max_tokens,
                    enabled_emotes = EXCLUDED.enabled_emotes,
                    updated_at    = now()
                RETURNING bot_name, persona, response_lang, refusal_style, max_tokens, enabled_emotes
                """,
                channel_id,
                merged["bot_name"],
                merged["persona"],
                merged["response_lang"],
                merged["refusal_style"],
                merged["max_tokens"],
                list(merged.get("enabled_emotes") or []),
            )
        _ai_settings_cache.invalidate(f"ai_settings:{channel_id}")
        d = dict(row)
        d["enabled_emotes"] = list(d.get("enabled_emotes") or [])
        return d

    def invalidate_cache(self, channel_id: str) -> None:
        _ai_settings_cache.invalidate(f"ai_settings:{channel_id}")
