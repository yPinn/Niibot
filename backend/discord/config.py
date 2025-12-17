"""Discord Bot 配置"""

import os

import discord


class BotConfig:
    """Bot 配置"""

    # 狀態: online, idle, dnd, invisible
    STATUS: str = os.getenv("DISCORD_STATUS", "")

    # 活動類型: playing, streaming, listening, watching, competing
    ACTIVITY_TYPE: str = os.getenv("DISCORD_ACTIVITY_TYPE", "")

    # 活動名稱
    ACTIVITY_NAME: str = os.getenv("DISCORD_ACTIVITY_NAME", "")

    # Streaming URL (僅當 ACTIVITY_TYPE 為 streaming 時需要)
    ACTIVITY_URL: str = os.getenv("DISCORD_ACTIVITY_URL", "")

    @classmethod
    def get_status(cls) -> discord.Status:
        """取得狀態"""
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        return status_map.get(cls.STATUS.lower(), discord.Status.online)

    @classmethod
    def get_activity(cls) -> discord.Activity | discord.Streaming | None:
        """取得活動"""
        if not cls.ACTIVITY_NAME:
            return None

        activity_type_lower = cls.ACTIVITY_TYPE.lower()

        # streaming 需要特殊處理，使用 discord.Streaming
        if activity_type_lower == "streaming":
            return discord.Streaming(name=cls.ACTIVITY_NAME, url=cls.ACTIVITY_URL)

        activity_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing,
        }

        activity_type = activity_map.get(
            activity_type_lower, discord.ActivityType.playing)
        return discord.Activity(type=activity_type, name=cls.ACTIVITY_NAME)
