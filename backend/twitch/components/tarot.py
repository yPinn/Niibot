import json
import random
from datetime import datetime
from hashlib import md5
from typing import TYPE_CHECKING

from twitchio.ext import commands

from core.config import DATA_DIR
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot

_CATEGORY_ALIASES: dict[str, list[str]] = {
    "love": ["l", "love", "感情"],
    "career": ["c", "career", "事業"],
    "finance": ["f", "finance", "財運"],
}
CATEGORY_MAP = {alias: cat for cat, aliases in _CATEGORY_ALIASES.items() for alias in aliases}


class TarotComponent(commands.Component):
    COMMANDS: list[dict] = [
        {"command_name": "tarot", "cooldown": 5, "aliases": "塔羅"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self._load_data()

    def _load_data(self) -> None:
        with open(DATA_DIR / "tarot.json", encoding="utf-8") as f:
            self.tarot_data = json.load(f)

    def _get_daily_card(self, user_id: str) -> tuple[str, bool]:
        today = datetime.now().strftime("%Y-%m-%d")
        seed = int(md5(f"{user_id}-{today}".encode()).hexdigest(), 16)

        random.seed(seed)
        card_ids = list(self.tarot_data["cards"].keys())
        card_id = random.choice(card_ids)
        is_reversed = random.choice([True, False])
        random.seed()

        return card_id, is_reversed

    @commands.command(aliases=["塔羅"])
    async def tarot(self, ctx: commands.Context, *, args: str | None = None) -> None:
        """每日塔羅占卜。用法: !塔羅 [感情/事業/財運]"""
        config = await check_command(
            self.cmd_repo, ctx, channel_repo=self.channel_repo, command_name="tarot"
        )
        if not config:
            return

        category = CATEGORY_MAP.get((args or "").strip().lower(), "general")

        user_id = ctx.chatter.id
        card_id, is_reversed = self._get_daily_card(user_id)

        card = self.tarot_data["cards"][card_id]
        orientation = "逆位" if is_reversed else "正位"
        info = card["reversed"] if is_reversed else card["upright"]

        keywords = "・".join(info["keywords"])
        meaning = info["meanings"].get(category, info["meanings"]["general"])
        full_meaning = meaning.replace("\n", "")

        await ctx.reply(f"🃏 {card['name']}({orientation}) | {keywords} — {full_meaning}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(TarotComponent(bot))


async def teardown(bot: commands.Bot) -> None: ...
