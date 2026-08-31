"""Regression tests for the repository environment-file generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("root_gen_env", _ROOT / "scripts" / "gen_env.py")
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
