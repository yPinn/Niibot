"""Regression tests for the repository environment-file generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("root_gen_env", _ROOT / "scripts" / "env" / "gen.py")
assert _SPEC is not None and _SPEC.loader is not None
gen_env = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gen_env
_SPEC.loader.exec_module(gen_env)


def test_docs_table_is_prettier_stable() -> None:
    variables = [
        gen_env.Var(key="A", scopes=["shared"], description="short"),
        gen_env.Var(key="LONGER_NAME", scopes=["shared"], description="long description"),
    ]

    rendered = gen_env.render_docs_table(variables)

    assert (
        "\n".join(
            [
                "| 變數          | 說明             |",
                "| ------------- | ---------------- |",
                "| `A`           | short            |",
                "| `LONGER_NAME` | long description |",
            ]
        )
        in rendered
    )


def test_frontend_url_docs_cover_public_tarot_assets() -> None:
    variables, _ = gen_env.load_registry()
    frontend_url = next(variable for variable in variables if variable.key == "FRONTEND_URL")

    assert frontend_url.description == "前端公開 URL"
    assert "公開素材" in frontend_url.help


def test_github_targets_follow_scope_and_short_file_names() -> None:
    variables, _ = gen_env.load_registry()
    by_key = {variable.key: variable for variable in variables}

    assert gen_env.github_targets(by_key["LOG_LEVEL"]) == ["variables_base"]
    assert gen_env.github_targets(by_key["ENVIRONMENT"]) == [
        "variables_prod",
        "variables_stg",
    ]


def test_nonprod_shared_credentials_are_explicit_and_env_scoped() -> None:
    variables, _ = gen_env.load_registry()
    shared = {variable.key for variable in variables if variable.nonprod_shared}

    assert shared == {
        "BOT_ID",
        "DISCORD_BOT_TOKEN",
        "DISCORD_PUBLIC_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "INSTAGRAM_SESSION_ID",
        "NIGHTBOT_CLIENT_ID",
        "NIGHTBOT_CLIENT_SECRET",
        "OPENROUTER_API_KEY",
        "RELEASES_GITHUB_TOKEN",
        "TWITCH_CLIENT_ID",
        "TWITCH_CLIENT_SECRET",
        "YOUTUBE_API_KEY",
    }
    assert all(variable.ci_scope == "env" for variable in variables if variable.nonprod_shared)
    assert gen_env.GITHUB_FILES["variables_stg"].endswith("/stg.env.example")


def test_runtime_examples_keep_registry_order_within_sections() -> None:
    variables, meta = gen_env.load_registry()

    rendered = gen_env.render_runtime_example("root", variables, meta)

    assert rendered.index("POSTGRES_USER=") < rendered.index("POSTGRES_PASSWORD=")
    assert rendered.index("POSTGRES_PASSWORD=") < rendered.index("POSTGRES_DB=")
    assert rendered.index("POSTGRES_DB=") < rendered.index("DOCKER_DATABASE_URL=")


def test_public_identifiers_are_github_variables() -> None:
    variables, _ = gen_env.load_registry()
    by_key = {variable.key: variable for variable in variables}
    public = {
        "POSTGRES_USER",
        "POSTGRES_DB",
        "FRONTEND_URL",
        "TWITCH_CLIENT_ID",
        "BOT_ID",
        "OWNER_ID",
        "CONDUIT_ID",
        "NIGHTBOT_CLIENT_ID",
        "DISCORD_PUBLIC_KEY",
    }

    for key in public:
        assert by_key[key].sensitive is False
        assert by_key[key].ci_source.startswith("var:")

    manifest = gen_env.build_manifest(variables)
    assert {
        "POSTGRES_USER",
        "POSTGRES_DB",
        "FRONTEND_URL",
        "API_URL",
        "TWITCH_CLIENT_ID",
    } <= set(manifest["required_variables"])


def test_registry_deploy_defaults_are_explicit_and_safe() -> None:
    variables, _ = gen_env.load_registry()
    by_key = {variable.key: variable for variable in variables}

    assert by_key["API_URL"].required is True
    assert by_key["SCRAPLING_ENVIRONMENT"].default == "development"
    assert by_key["GROQ_MODEL"].default == "openai/gpt-oss-120b"
    assert by_key["GEMINI_MODEL"].default == "gemini-3.5-flash"
    assert by_key["OPENROUTER_MODEL"].default == "inclusionai/ling-3.0-flash-vl:free"
    assert by_key["PAYMENT_ENCRYPTION_KEY"].required is True
    assert by_key["PAYMENT_ENCRYPTION_KEY"].value_format == "fernet"
    assert by_key["TWITCH_TOKEN_ENCRYPTION_KEY"].value_format == "fernet"
    assert by_key["DEPLOY_WEBHOOK_URL"].ci_conditional is True

    manifest = gen_env.build_manifest(variables)
    assert manifest["ci"]["PAYMENT_ENCRYPTION_KEY"]["format"] == "fernet"
    assert manifest["ci"]["TWITCH_TOKEN_ENCRYPTION_KEY"]["format"] == "fernet"


def test_optional_runtime_values_are_commented_until_enabled() -> None:
    variables, meta = gen_env.load_registry()

    shared = gen_env.render_runtime_example("shared", variables, meta)
    discord = gen_env.render_runtime_example("discord", variables, meta)
    scrapling = gen_env.render_runtime_example("scrapling", variables, meta)
    frontend = gen_env.render_runtime_example("frontend", variables, meta)

    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "YOUTUBE_API_KEY"):
        assert f"# {key}=" in shared
        assert f"\n{key}=" not in shared
    assert "# DISCORD_ACTIVITY_NAME=" in discord
    assert "DISCORD_SYNC_COMMANDS" not in discord
    assert "# THREADS_SESSION_ID=" in scrapling
    assert "# VITE_DISCORD_BOT_INVITE_URL=" in frontend
    assert "# VITE_SUPPORT_ECPAY_URL=" in frontend
    assert "\nVITE_DISCORD_COMMUNITY_URL=" in frontend


def test_github_examples_comment_conditional_values_but_keep_required_values_active() -> None:
    variables, meta = gen_env.load_registry()

    base_secrets = gen_env.render_github_example("secrets_base", variables, meta)
    stg_secrets = gen_env.render_github_example("secrets_stg", variables, meta)
    prod_secrets = gen_env.render_github_example("secrets_prod", variables, meta)
    prod_variables = gen_env.render_github_example("variables_prod", variables, meta)

    assert "GROQ_API_KEY" not in base_secrets
    assert "# GROQ_API_KEY=" in stg_secrets
    assert "# GROQ_API_KEY=" in prod_secrets
    assert "PAYMENT_ENCRYPTION_KEY=" in prod_secrets
    assert "# DEPLOY_WEBHOOK_URL=" in prod_secrets
    assert "# DISCORD_ACTIVITY_NAME=尖尖哇嘎奈..." in prod_variables
    assert "DISCORD_DESCRIPTION" not in prod_variables


def test_manifest_declares_all_or_none_configuration_groups() -> None:
    variables, _ = gen_env.load_registry()

    manifest = gen_env.build_manifest(variables)

    assert manifest["ci_groups"]["groq"] == {
        "members": ["GROQ_API_KEY", "GROQ_MODEL"],
        "activators": ["GROQ_API_KEY"],
    }
    assert manifest["ci_groups"]["nightbot"] == {
        "members": ["NIGHTBOT_CLIENT_ID", "NIGHTBOT_CLIENT_SECRET"],
        "activators": ["NIGHTBOT_CLIENT_ID", "NIGHTBOT_CLIENT_SECRET"],
    }
    assert manifest["ci"]["GROQ_MODEL"]["default"] == "openai/gpt-oss-120b"


def test_env_scoped_ci_examples_do_not_define_unused_base_values() -> None:
    variables, _ = gen_env.load_registry()

    for variable in variables:
        if variable.ci_scope == "env":
            assert "base" not in variable.ci_example, variable.key


def test_registry_descriptions_stay_concise() -> None:
    variables, _ = gen_env.load_registry()

    for variable in variables:
        assert variable.description, variable.key
        assert "\n" not in variable.description, variable.key
        assert len(variable.description) <= 40, variable.key
