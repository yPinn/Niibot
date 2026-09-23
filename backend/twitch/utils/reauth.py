"""Reauth message helpers for scope-missing Helix errors.

Notification is state-transition driven, not time-based: Bot._mark_reauth_required
(see core/_notify_mixin.py) sends the chat message exactly once, the moment a
channel newly enters _needs_reauth. Callers here only need to detect the error
and hand the channel off to that single entry point — no cooldown bookkeeping.

Usage in a component:
    from utils.reauth import is_scope_error

    response = await self.bot._http.post_chat_shoutout(...)
    if is_scope_error(response):
        await self.bot._mark_reauth_required(channel_id)
        return
"""

from core.config import get_settings


def is_scope_error(obj: object) -> bool:
    """Return True if a response or exception indicates a missing OAuth scope.

    Handles both httpx.Response objects and TwitchIO HTTPException exceptions,
    which carry .status (int) and .message (str) rather than .status_code.
    """
    if obj is None:
        return False
    status = getattr(obj, "status_code", None) or getattr(obj, "status", None)
    if status != 401:
        return False
    # Named attributes first (fastest, covers TwitchIO HTTPException)
    for attr in ("message", "reason"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and "Missing scope" in val:
            return True
    # httpx.Response: parse JSON body
    try:
        body = obj.json() if callable(getattr(obj, "json", None)) else {}  # type: ignore[attr-defined]
        if "Missing scope" in body.get("message", ""):
            return True
    except Exception:
        pass
    # Last resort: stringify
    return "Missing scope" in str(obj)


def build_reauth_message(broadcaster_login: str) -> str:
    url = get_settings().frontend_url.rstrip("/")
    return f"@{broadcaster_login} 授權過期了，麻煩重新登入 {url}/login"
