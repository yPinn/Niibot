#!/usr/bin/env python3
"""Rebuild one runtime env set from examples while preserving known values."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("dev", "stg", "prod")
RUNTIME_NAMES = {
    "dev": "development",
    "stg": "staging",
    "prod": "production",
}
TEMPLATES = {
    "root": Path(".env"),
    "shared": Path("backend/shared.env"),
    "api": Path("backend/api/.env"),
    "twitch": Path("backend/twitch/.env"),
    "discord": Path("backend/discord/.env"),
    "scrapling": Path("backend/scrapling/.env"),
    "frontend": Path("frontend/.env"),
}
BACKEND_SCOPES = {"api", "twitch", "discord"}
ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def _actual_path(template: Path, target: str) -> Path | None:
    if template.as_posix() == "frontend/.env":
        return template if target == "dev" else None
    if template.as_posix() == ".env":
        return Path(f".env.{target}")
    if template.name == "shared.env":
        return template.with_name(f"shared.{target}.env")
    return template.with_name(f".env.{target}")


def _active_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = ASSIGNMENT.match(line.strip())
        if not match or match.group(1) is not None:
            continue
        key, value = match.group(2), match.group(3)
        if key in values:
            raise ValueError(f"{path}: duplicate {key} at line {line_no}")
        values[key] = value
    return values


def _expected_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match and match.group(2) not in keys:
            keys.append(match.group(2))
    return keys


def _routes(root: Path) -> dict[str, set[str]]:
    registry = tomllib.loads((root / "env.registry.toml").read_text(encoding="utf-8"))
    routes: dict[str, set[str]] = {}
    for variable in registry.get("var", []):
        name = variable.get("name", variable["key"])
        routes.setdefault(name, set()).update(variable.get("scopes", []))
    return routes


def _render(example: Path, scope: str, values: dict[tuple[str, str], str]) -> str:
    lines = example.read_text(encoding="utf-8").splitlines()
    emitted: set[str] = set()
    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line.strip())
        if not match:
            continue
        key = match.group(2)
        if key in emitted:
            continue
        emitted.add(key)
        identity = (scope, key)
        if identity in values:
            lines[index] = f"{key}={values[identity]}"
    return "\n".join(lines) + "\n"


def normalized_outputs(root: Path, target: str) -> dict[Path, str]:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")

    files: dict[str, tuple[Path, Path]] = {}
    expected: dict[str, set[str]] = {}
    for scope, template in TEMPLATES.items():
        example = root / f"{template}.example"
        actual_rel = _actual_path(template, target)
        if not example.is_file() or actual_rel is None:
            continue
        actual = root / actual_rel
        if not actual.is_file():
            raise ValueError(f"{actual}: missing; run env init {target} first")
        files[scope] = (actual, example)
        expected[scope] = set(_expected_keys(example))

    routes = _routes(root)
    values: dict[tuple[str, str], tuple[str, str]] = {}
    for source_scope, (actual, _example) in files.items():
        for key, value in _active_values(actual).items():
            if key in expected[source_scope]:
                destination = source_scope
            else:
                candidates = routes.get(key, set()) & files.keys()
                if source_scope in BACKEND_SCOPES and "shared" in candidates:
                    destination = "shared"
                elif len(candidates) == 1:
                    destination = next(iter(candidates))
                elif candidates:
                    raise ValueError(f"{actual}: ambiguous destination for {key}")
                else:
                    raise ValueError(f"{actual}: unknown key {key}")

            identity = (destination, key)
            if identity not in values or (not values[identity][0] and value):
                values[identity] = (value, source_scope)
                continue
            current, current_source = values[identity]
            if value and current and value != current:
                raise ValueError(
                    f"conflicting values for {key} in {current_source} and {source_scope}"
                )

    runtime = RUNTIME_NAMES[target]
    for scope, keys in expected.items():
        if "ENVIRONMENT" in keys:
            values[(scope, "ENVIRONMENT")] = (runtime, "generated")

    plain_values = {identity: value for identity, (value, _source) in values.items()}
    return {
        actual: _render(example, scope, plain_values)
        for scope, (actual, example) in files.items()
    }


def _write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument(
        "--check", action="store_true", help="report drift without writing"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = normalized_outputs(ROOT, args.target)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    changed = [
        path
        for path, content in outputs.items()
        if path.read_text(encoding="utf-8") != content
    ]
    if args.check:
        for path in changed:
            print(f"drift: {path.relative_to(ROOT)}")
        return int(bool(changed))
    for path in changed:
        _write_atomic(path, outputs[path])
        print(f"synced {path.relative_to(ROOT)}")
    if not changed:
        print(f"ok: {args.target} env files already match their examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
