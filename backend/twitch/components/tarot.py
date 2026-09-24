import json
import logging
from typing import TYPE_CHECKING

import twitchio.ext.commands as commands

from core.component import BotComponent
from core.config import DATA_DIR
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository
from shared.repositories.community_overlay import CommunityOverlayRepository
from shared.services.community_overlay import CommunityOverlayService
from shared.tarot_assets import load_tarot_deck_catalog
from shared.tarot_overlay import build_tarot_overlay_payload
from shared.tarot_reading import (
    TAROT_CATEGORY_LABELS,
    get_daily_tarot_draw,
    normalize_tarot_category,
)

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)

_TWITCH_MESSAGE_LIMIT = 500


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    if limit == 1:
        return "…"
    return f"{text[: limit - 1].rstrip()}…"


def format_tarot_reply(
    *,
    category_label: str,
    card_name: str,
    orientation: str,
    keywords: str,
    meaning: str,
    advice: str,
) -> str:
    """Keep the full reading in chat while respecting Twitch's 500-character limit."""
    labels = "｜關鍵字：｜解讀：｜今日建議："
    header = _truncate(f"🃏 {category_label}｜{card_name}（{orientation}）", 120)
    keyword_text = _truncate(keywords, 120)
    available = max(0, _TWITCH_MESSAGE_LIMIT - len(header) - len(keyword_text) - len(labels))
    advice_budget = min(len(advice), min(140, available // 3))
    meaning_budget = available - advice_budget
    reply = (
        f"{header}｜關鍵字：{keyword_text}｜解讀：{_truncate(meaning, meaning_budget)}"
        f"｜今日建議：{_truncate(advice, advice_budget)}"
    )
    return _truncate(reply, _TWITCH_MESSAGE_LIMIT)


def format_tarot_topic_error(value: str) -> str:
    topic = _truncate(value.strip(), 20)
    return f"找不到「{topic}」這個主題。可用：綜合、感情、事業、財運。例：!塔羅 感情"


class TarotComponent(BotComponent):
    COMMANDS: list[dict] = [
        {"command_name": "tarot", "cooldown": 5, "aliases": "塔羅"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        pool = self.bot.token_database  # type: ignore[attr-defined]
        self.cmd_repo = CommandConfigRepository(pool)
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self.overlay = CommunityOverlayService(CommunityOverlayRepository(pool))
        self._load_data()

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool
        self.overlay.repository.pool = pool

    def _load_data(self) -> None:
        with open(DATA_DIR / "tarot.json", encoding="utf-8") as f:
            self.tarot_data = json.load(f)
        self.tarot_decks = load_tarot_deck_catalog(
            DATA_DIR / "tarot_decks.json",
            expected_card_ids=set(self.tarot_data["cards"]),
        )

    def _get_daily_card(self, user_id: str, category: str) -> tuple[str, bool]:
        return get_daily_tarot_draw(
            self.tarot_data["cards"],
            user_id=user_id,
            category=category,
        )

    @commands.command(aliases=["塔羅"])
    async def tarot(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """每日塔羅。用法：!塔羅 [綜合／感情／事業／財運]"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="tarot"
        )
        if not config:
            return

        raw_category = (args or "").strip()
        category = normalize_tarot_category(raw_category)
        if category is None:
            await self._ctx_reply(ctx, format_tarot_topic_error(raw_category))
            return

        user_id = str(ctx.chatter.id)
        card_id, is_reversed = self._get_daily_card(user_id, category)

        card = self.tarot_data["cards"][card_id]
        orientation = "逆位" if is_reversed else "正位"
        info = card["reversed"] if is_reversed else card["upright"]

        keywords = "・".join(info["keywords"])
        meaning = info["meanings"].get(category, info["meanings"]["general"])
        full_meaning = meaning.replace("\n", "")
        overlay_payload = build_tarot_overlay_payload(
            tarot_data=self.tarot_data,
            deck_catalog=self.tarot_decks,
            card_id=card_id,
            is_reversed=is_reversed,
            category=category,
        )

        await self._ctx_reply(
            ctx,
            format_tarot_reply(
                category_label=TAROT_CATEGORY_LABELS[category],
                card_name=card["name"],
                orientation=orientation,
                keywords=keywords,
                meaning=full_meaning,
                advice=info["advice"].replace("\n", ""),
            ),
        )
        try:
            await self.overlay.publish_tarot(
                channel_id=ctx.channel.id,
                actor_user_id=str(ctx.chatter.id),
                actor_display_name=ctx.chatter.display_name or ctx.chatter.name or "觀眾",
                payload=overlay_payload,
            )
        except Exception:
            LOGGER.exception(
                "Tarot overlay publish failed",
                extra={"channel_id": ctx.channel.id, "user_id": str(ctx.chatter.id)},
            )
        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, "tarot")
        except Exception as e:
            LOGGER.debug("usage count failed for tarot: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(TarotComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
