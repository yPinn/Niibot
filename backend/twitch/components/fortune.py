import json
import logging
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import twitchio.ext.commands as commands

from core.component import BotComponent
from core.config import DATA_DIR
from core.guards import check_command
from shared.repositories.command_config import CommandConfigRepository

if TYPE_CHECKING:
    from core.bot import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class FortuneComponent(BotComponent):
    COMMANDS: list[dict] = [
        {"command_name": "fortune", "cooldown": 5, "aliases": "運勢"},
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: Bot = bot  # type: ignore[assignment]
        self.cmd_repo = CommandConfigRepository(self.bot.token_database)  # type: ignore[attr-defined]
        self.channel_repo = self.bot.channels  # type: ignore[attr-defined]
        self._load_data()

    def refresh_pool(self, pool) -> None:
        self.cmd_repo.pool = pool

    def _load_data(self) -> None:
        fortune_path = DATA_DIR / "fortune.json"
        with open(fortune_path, encoding="utf-8") as f:
            self.fortune_data = json.load(f)

    def _get_fortune_level(self, date_modifier: float = 1.0) -> str:
        levels = list(self.fortune_data["fortune_levels"].keys())
        weights = [
            self.fortune_data["fortune_levels"][level]["weight"] * date_modifier for level in levels
        ]
        result = random.choices(levels, weights=weights, k=1)[0]
        return str(result)

    def _get_date_bonus(self) -> tuple[str | None, float]:
        today = datetime.now(UTC)
        date_key = f"{today.month}-{today.day}"

        special_dates = self.fortune_data.get("special_dates", {})
        if date_key in special_dates:
            event = special_dates[date_key]
            return event["name"], event["modifier"]
        return None, 1.0

    def _add_twitch_emotes(self, text: str, category: str) -> str:
        emote_map = {
            "好": "BloodTrail",
            "中": "SeemsGood",
            "差": "ResidentSleeper",
        }
        emote = emote_map.get(category, "")
        if emote and emote not in text:
            return f"{text} {emote}"
        return text

    @commands.command(name="fortune", aliases=["運勢"])
    async def fortune(self, ctx: commands.Context["Bot"]) -> None:
        """運勢占卜指令

        用法:
            !fortune - 查看今日運勢
            !運勢 - 同上（中文別名）
        """
        config = await check_command(self.cmd_repo, ctx, "fortune", self.channel_repo)
        if not config:
            return

        user = ctx.chatter.display_name or ctx.chatter.name or ""

        try:
            special_event, date_modifier = self._get_date_bonus()
            fortune_level = self._get_fortune_level(date_modifier)
            level_data = self.fortune_data["fortune_levels"][fortune_level]
            category = level_data["category"]
            description = level_data["description"]

            fortune_details = self.fortune_data["fortune_details"][category]
            career = self._add_twitch_emotes(random.choice(fortune_details["事業"]), category)
            wealth = random.choice(fortune_details["財運"])
            love = random.choice(fortune_details["愛情"])

            lucky_data = self.fortune_data["lucky_elements"][category]
            lucky_color = random.choice(lucky_data["colors"])
            lucky_number = random.choice(lucky_data["numbers"])
            lucky_hour = random.choice(lucky_data["hours"])

            parts = [f"🔮 {user} 的運勢占卜"]
            parts.append(f"運勢：{fortune_level} {description}")

            if special_event:
                parts.append(f"{special_event}，運勢有額外加成！")

            parts.extend(
                [
                    f"事業：{career}",
                    f"財運：{wealth}",
                    f"愛情：{love}",
                    f"🍀 幸運色：{lucky_color}・數字：{lucky_number}・吉時：{lucky_hour}",
                ]
            )

            message = " | ".join(parts)
            await self._ctx_reply(ctx, message)
            LOGGER.debug(f"User {user} fortune: {fortune_level}")

        except Exception as e:
            LOGGER.error(f"Fortune reading error: {e}")
            await self._ctx_reply(ctx, "占卜過程中發生神秘干擾，請稍後再試 BloodTrail")
            return

        try:
            await self.cmd_repo.increment_usage_count(ctx.channel.id, "fortune")
        except Exception as e:
            LOGGER.warning(f"Failed to increment usage count for fortune: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_component(FortuneComponent(bot))
    LOGGER.info("Fortune component loaded")


async def teardown(bot: commands.Bot) -> None:
    LOGGER.info("Fortune component unloaded")
