"""Twitch API client service.

Token types:
- App Access Token: For public endpoints (users, streams, games). Auto-fetched and cached.
- User Access Token: For user-specific endpoints (channel:bot, redemptions).
  Requires OAuth flow, stored in DB, can be refreshed.

The implementation is split into per-domain mixins under ``services._twitch_api``;
this module composes them into the public ``TwitchAPIClient`` and re-exports the
names callers import from here.
"""

from services._twitch_api._base import HELIX_BASE, OAUTH_BASE, _TwitchAPIBase
from services._twitch_api._channel import _ChannelMixin
from services._twitch_api._moderation import _ModerationMixin
from services._twitch_api._oauth import TokenRefreshResult, _OAuthMixin
from services._twitch_api._users import _UsersMixin

__all__ = ["HELIX_BASE", "OAUTH_BASE", "TokenRefreshResult", "TwitchAPIClient"]


class TwitchAPIClient(_OAuthMixin, _UsersMixin, _ModerationMixin, _ChannelMixin, _TwitchAPIBase):
    """Client for interacting with Twitch API.

    Manages a shared httpx client for connection reuse and caches
    the app access token to avoid redundant token requests.
    """
