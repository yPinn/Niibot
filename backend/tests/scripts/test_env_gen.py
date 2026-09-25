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

    assert "Discord Tarot embed" in frontend_url.description


def test_github_targets_follow_scope_and_short_file_names() -> None:
    variables, _ = gen_env.load_registry()
    by_key = {variable.key: variable for variable in variables}

    assert gen_env.github_targets(by_key["LOG_LEVEL"]) == ["variables_base"]
    assert gen_env.github_targets(by_key["ENVIRONMENT"]) == [
        "variables_prod",
        "variables_stg",
    ]
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
    assert {"POSTGRES_USER", "POSTGRES_DB", "FRONTEND_URL", "TWITCH_CLIENT_ID"} <= set(
        manifest["required_variables"]
    )
