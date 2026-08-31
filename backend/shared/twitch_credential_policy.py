"""Credential strategy selected for TwitchIO's user-id keyed token store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class TwitchCredentialPlan:
    """How credentials must be loaded for one broadcaster/bot pairing."""

    strategy: Literal["separate", "union"]
    required_scopes_by_user: dict[str, frozenset[str]]
    mirrored_token_roles: frozenset[str] = frozenset()


def build_credential_plan(
    *,
    broadcaster_user_id: str,
    bot_user_id: str,
    broadcaster_scopes: set[str] | frozenset[str],
    bot_scopes: set[str] | frozenset[str],
) -> TwitchCredentialPlan:
    """Choose a safe strategy for TwitchIO 3.3's ``_tokens[user_id]`` map.

    Distinct Twitch identities can remain independent. If one identity fills
    both roles, loading two refresh credentials would silently overwrite one;
    the account must therefore authorize the union and both DB role rows mirror
    one canonical token lifecycle.
    """
    if broadcaster_user_id != bot_user_id:
        return TwitchCredentialPlan(
            strategy="separate",
            required_scopes_by_user={
                broadcaster_user_id: frozenset(broadcaster_scopes),
                bot_user_id: frozenset(bot_scopes),
            },
        )

    return TwitchCredentialPlan(
        strategy="union",
        required_scopes_by_user={broadcaster_user_id: frozenset(broadcaster_scopes | bot_scopes)},
        mirrored_token_roles=frozenset({"broadcaster", "bot"}),
    )
