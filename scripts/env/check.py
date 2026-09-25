#!/usr/bin/env python3
"""Validate an env file against its generated example without reading values aloud."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=")
ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("dev", "stg", "prod", "gh-stg", "gh-prod")


def keys(path: Path) -> list[str]:
    found: list[str] = []
    active: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = ASSIGNMENT.match(line.strip())
        if not match:
            continue
        commented, key = match.groups()
        if key in active and commented is None:
            raise ValueError(f"{path}: duplicate {key} at line {line_no}")
        if key not in found:
            found.append(key)
        if commented is None:
            active.add(key)
    return found


def validate(path: Path, example: Path) -> list[str]:
    actual = keys(path)
    expected = keys(example)
    errors: list[str] = []
    missing = [key for key in expected if key not in actual]
    extra = [key for key in actual if key not in expected]
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown keys: {', '.join(extra)}")
    if not missing and not extra and actual != expected:
        errors.append("key order differs from generated example")
    return errors


def _runtime_path(template: Path, env: str) -> Path | None:
    if template.as_posix() == "frontend/.env":
        return template if env == "dev" else None
    if template.as_posix() == ".env":
        return Path(f".env.{env}")
    if template.name == "shared.env":
        return template.with_name(f"shared.{env}.env")
    return template.with_name(f".env.{env}")


def target_pairs(root: Path, target: str) -> list[tuple[Path, Path]]:
    if target.startswith("gh-"):
        env = target.removeprefix("gh-")
        return [
            (
                root / f".github/{kind}/{scope}.env",
                root / f".github/{kind}/{scope}.env.example",
            )
            for kind in ("variables", "secrets")
            for scope in ("base", env)
        ]

    manifest = json.loads((root / "env.manifest.json").read_text(encoding="utf-8"))
    pairs: list[tuple[Path, Path]] = []
    for rel in manifest["runtime_files"]:
        template = Path(rel)
        actual = _runtime_path(template, target)
        if actual is not None:
            pairs.append((root / actual, root / f"{template}.example"))
    return pairs


def validate_target(root: Path, target: str) -> list[str]:
    errors: list[str] = []
    for path, example in target_pairs(root, target):
        if not path.is_file():
            errors.append(f"{path}: missing")
            continue
        if not example.is_file():
            errors.append(f"{example}: missing example")
            continue
        try:
            errors.extend(f"{path}: {error}" for error in validate(path, example))
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 1 and args[0] in TARGETS:
        errors = validate_target(ROOT, args[0])
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"ok: {args[0]} env structure")
        return 0
    if len(args) != 2:
        print(
            "usage: check.py <dev|stg|prod|gh-stg|gh-prod>\n"
            "       check.py <env-file> <example-file>",
            file=sys.stderr,
        )
        return 2
    path, example = map(Path, args)
    if not path.is_file() or not example.is_file():
        print("error: env file or example is missing", file=sys.stderr)
        return 1
    try:
        errors = validate(path, example)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"error: {path}: {error}", file=sys.stderr)
        return 1
    print(f"ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
