"""Mod-request message helper — asks chat for /mod once the bot is confirmed to lack it.

Notification is state-transition driven, not time-based: Bot._check_bot_mod_status
sends the message exactly once, the moment a channel newly enters _bot_not_mod
(see core/bot.py), plus a once-per-stream reminder on stream online — mirrors
utils.reauth's build_reauth_message / _mark_reauth_required split. Chat-message
handling only blocks silently and never sends from here directly.
"""


def build_mod_request_message(broadcaster_login: str, bot_login: str) -> str:
    return f"@{broadcaster_login} 好想要那把酷酷的大劍喔，可以 /mod {bot_login} 給我一把嗎 GoldPLZ"
