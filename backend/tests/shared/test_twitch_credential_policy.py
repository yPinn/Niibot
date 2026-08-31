"""Credential strategy selected by the TwitchIO dual-token spike."""

from shared.twitch_credential_policy import build_credential_plan


def test_distinct_accounts_keep_independent_role_credentials():
    plan = build_credential_plan(
        broadcaster_user_id="streamer",
        bot_user_id="niibot",
        broadcaster_scopes={"channel:read:redemptions"},
        bot_scopes={"user:write:chat"},
    )

    assert plan.strategy == "separate"
    assert plan.required_scopes_by_user == {
        "streamer": frozenset({"channel:read:redemptions"}),
        "niibot": frozenset({"user:write:chat"}),
    }


def test_same_identity_uses_one_union_scope_credential():
    plan = build_credential_plan(
        broadcaster_user_id="same-user",
        bot_user_id="same-user",
        broadcaster_scopes={"channel:read:redemptions", "user:read:chat"},
        bot_scopes={"user:read:chat", "user:write:chat"},
    )

    assert plan.strategy == "union"
    assert plan.required_scopes_by_user == {
        "same-user": frozenset({"channel:read:redemptions", "user:read:chat", "user:write:chat"})
    }
    assert plan.mirrored_token_roles == frozenset({"broadcaster", "bot"})
