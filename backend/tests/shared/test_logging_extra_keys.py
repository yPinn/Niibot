"""No ``extra=`` key may collide with a LogRecord attribute.

``logging.Logger.makeRecord`` raises ``KeyError`` when ``extra`` carries a name
the record already owns — ``created``, ``module``, ``name``, ``process`` and so
on. It is a landmine rather than an ordinary bug for two reasons: the call site
looks perfectly reasonable, and ``Logger.info`` short-circuits on
``isEnabledFor`` before building the record, so under the suite's default
WARNING level an offending INFO line stays silent and only fails in an
environment that runs at INFO.

This walks the AST instead of relying on the line being exercised.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {"__pycache__", ".venv", ".cache", ".tmp", "node_modules"}

# Whatever LogRecord.__init__ sets, plus the two names Formatter adds later.
RESERVED: frozenset[str] = frozenset(
    logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None).__dict__
) | {"message", "asctime"}


def _python_files() -> list[Path]:
    return [p for p in _BACKEND.rglob("*.py") if not _SKIP_DIRS.intersection(p.parts)]


def _reserved_extra_keys(path: Path) -> list[tuple[int, str]]:
    """Reserved names used as literal keys of an ``extra=`` dict in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # not ours to police
        return []

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and key.value in RESERVED:
                    found.append((node.lineno, str(key.value)))
    return found


def test_reserved_set_contains_the_usual_suspects():
    # Guards the guard: if a Python release renames these, the scan below would
    # silently stop checking anything useful.
    assert {"created", "name", "module", "message", "asctime"} <= RESERVED


def test_no_log_extra_shadows_a_logrecord_attribute():
    offenders = [
        f"{path.relative_to(_BACKEND).as_posix()}:{line} uses extra={{{key!r}: ...}}"
        for path in _python_files()
        for line, key in _reserved_extra_keys(path)
    ]
    assert not offenders, "logging would raise KeyError here:\n  " + "\n  ".join(offenders)
