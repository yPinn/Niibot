#!/usr/bin/env python3
"""Classify changed repository paths for the GitHub Actions CI workflow.

The classifier is deliberately conservative: an unrecognised repository path
causes both expensive suites to run. Only explicitly documented non-runtime
paths may use the preflight-only fast path.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from typing import NamedTuple


class Decision(NamedTuple):
    frontend: bool
    backend: bool
    reason: str


CI_CONTROL_PATHS = frozenset(
    {
        ".github/workflows/ci.yml",
        "scripts/ci_changed_paths.py",
    }
)

PREFLIGHT_ONLY_FILES = frozenset(
    {
        ".env.example",
        ".github/dependabot.yml",
        ".gitattributes",
        ".gitignore",
        ".gitleaks.toml",
        ".impeccable.md",
        ".markdownlint.json",
        ".markdownlintignore",
        ".nvmrc",
        ".prettierignore",
        ".secretlintignore",
        ".secretlintrc.json",
        "CLAUDE.md",
        "LICENSE",
        "PRODUCT.md",
        "README.md",
        "commitlint.config.js",
        "env.manifest.json",
        "env.registry.toml",
        "package-lock.json",
        "package.json",
        "scripts/gen_env.py",
    }
)

PREFLIGHT_ONLY_PREFIXES = (
    ".github/ISSUE_TEMPLATE/",
    ".github/PULL_REQUEST_TEMPLATE/",
    ".github/secrets/",
    ".github/variables/",
    ".husky/",
    "docs/",
)


def _normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_preflight_only(path: str) -> bool:
    return path in PREFLIGHT_ONLY_FILES or path.startswith(PREFLIGHT_ONLY_PREFIXES)


def classify_paths(
    paths: Iterable[str],
    *,
    event_name: str,
    draft: bool,
) -> Decision:
    """Return the expensive suites required for this workflow event."""

    if event_name != "pull_request":
        return Decision(True, True, "protected-or-manual")

    if draft:
        return Decision(False, False, "draft")

    normalized_paths = [path for raw in paths if (path := _normalize_path(raw))]

    if any(path in CI_CONTROL_PATHS for path in normalized_paths):
        return Decision(True, True, "ci-control-plane")

    frontend = any(path.startswith("frontend/") for path in normalized_paths)
    backend = any(path.startswith("backend/") for path in normalized_paths)

    known_paths = [
        path
        for path in normalized_paths
        if path.startswith(("frontend/", "backend/")) or _is_preflight_only(path)
    ]
    if len(known_paths) != len(normalized_paths):
        return Decision(True, True, "conservative-fallback")

    if frontend or backend:
        return Decision(frontend, backend, "changed-paths")

    if normalized_paths:
        return Decision(False, False, "preflight-only")

    return Decision(True, True, "conservative-fallback")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, dest="event_name")
    parser.add_argument("--draft", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    decision = classify_paths(
        sys.stdin,
        event_name=args.event_name,
        draft=args.draft,
    )
    print(f"frontend={str(decision.frontend).lower()}")
    print(f"backend={str(decision.backend).lower()}")
    print(f"reason={decision.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
