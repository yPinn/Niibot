"""Birthday feature constants."""

from datetime import timedelta, timezone

import discord

# Timezone
TZ_UTC8 = timezone(timedelta(hours=8))

# Theme
BIRTHDAY_COLOR = discord.Color.from_str("#FF7F50")

# Defaults
DEFAULT_MESSAGE_TEMPLATE = "今天是 {users} 的生日，請各位送上祝福！"
DEFAULT_CHANNEL_NAME = "生日麻吉"
DEFAULT_ROLE_NAME = "今天我生日"

# Assets
BIRTHDAY_THUMBNAIL = "https://cdn.discordapp.com/attachments/1331063972996186192/1466317496813359125/birthday.jpg"
