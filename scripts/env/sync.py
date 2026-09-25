#!/usr/bin/env python3
"""Rebuild local env files from examples while preserving known values."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import tomllib
from collections.abc import Collection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TARGETS = ("dev", "stg", "prod")
TARGETS = (*RUNTIME_TARGETS, "gh")
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
GITHUB_KINDS = ("variables", "secrets")
GITHUB_SCOPES = ("base", "stg", "prod")
ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def _actual_path(template: Path, target: str) -> Path | None:
    if template.as_posix() == "frontend/.env":
        return Path("frontend/.env.dev") if target == "dev" else None
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


def _has_value(value: str) -> bool:
    return value.strip() not in {"", "''", '""'}


def _routes(root: Path) -> dict[str, set[str]]:
    registry = tomllib.loads((root / "env.registry.toml").read_text(encoding="utf-8"))
    routes: dict[str, set[str]] = {}
    for variable in registry.get("var", []):
        name = variable.get("name", variable["key"])
        routes.setdefault(name, set()).update(variable.get("scopes", []))
    return routes


def _staging_nonprod_values(root: Path, scopes: Collection[str]) -> dict[tuple[str, str], str]:
    registry = tomllib.loads((root / "env.registry.toml").read_text(encoding="utf-8"))
    sources: dict[str, dict[str, str]] = {}
    values: dict[tuple[str, str], str] = {}
    for variable in registry.get("var", []):
        if not variable.get("nonprod_shared"):
            continue
        ci = variable.get("ci", {})
        if ci.get("scope") != "env":
            raise ValueError(f"{variable['key']}: nonprod_shared requires env-scoped CI")
        kind, separator, source_key = ci.get("source", "").partition(":")
        source_dirs = {"var": "variables", "secret": "secrets"}
        if not separator or kind not in source_dirs:
            raise ValueError(f"{variable['key']}: nonprod_shared requires a var or secret source")
        if kind not in sources:
            source_path = root / ".github" / source_dirs[kind] / "stg.env"
            if not source_path.is_file():
                raise ValueError(f"{source_path}: missing")
            sources[kind] = _active_values(source_path)
        destinations = set(variable.get("scopes", [])) & scopes
        if len(destinations) != 1:
            raise ValueError(f"{variable['key']}: nonprod_shared requires one runtime scope")
        destination = next(iter(destinations))
        name = variable.get("name", variable["key"])
        values[(destination, name)] = sources[kind].get(source_key, "")
    return values


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
        if identity in values and _has_value(values[identity]):
            lines[index] = f"{key}={values[identity]}"
    return "\n".join(lines) + "\n"


def _runtime_outputs(root: Path, target: str, *, from_stg: bool = False) -> dict[Path, str]:
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

    if from_stg:
        if target != "dev":
            raise ValueError("--from-stg is only valid for target dev")
        for identity, value in _staging_nonprod_values(root, files.keys()).items():
            values[identity] = (value, "github/stg")

    plain_values = {identity: value for identity, (value, _source) in values.items()}
    return {
        actual: _render(example, scope, plain_values) for scope, (actual, example) in files.items()
    }


def _github_files(root: Path) -> dict[tuple[str, str], tuple[Path, Path]]:
    files: dict[tuple[str, str], tuple[Path, Path]] = {}
    for kind in GITHUB_KINDS:
        for scope in GITHUB_SCOPES:
            actual = root / ".github" / kind / f"{scope}.env"
            example = actual.with_suffix(".env.example")
            if not example.is_file():
                raise ValueError(f"{example}: missing")
            if not actual.is_file():
                raise ValueError(f"{actual}: missing")
            files[(kind, scope)] = (actual, example)
    return files


def _one_value(
    key: str,
    candidates: list[tuple[tuple[str, str], dict[str, str]]],
) -> str | None:
    found = [(identity, values[key]) for identity, values in candidates if key in values]
    nonempty = {value for _identity, value in found if value}
    if len(nonempty) > 1:
        sources = ", ".join(f"{kind}/{scope}" for (kind, scope), _value in found)
        raise ValueError(f"conflicting values for {key} in {sources}")
    if nonempty:
        return next(iter(nonempty))
    return "" if found else None


def github_unknown_keys(root: Path) -> list[str]:
    files = _github_files(root)
    expected = {
        key for _identity, (_actual, example) in files.items() for key in _expected_keys(example)
    }
    actual = {key for _identity, (path, _example) in files.items() for key in _active_values(path)}
    return sorted(actual - expected)


def _github_outputs(root: Path, *, drop_unknown: bool) -> dict[Path, str]:
    files = _github_files(root)
    source_values = {
        identity: _active_values(actual) for identity, (actual, _example) in files.items()
    }
    expected = {identity: _expected_keys(example) for identity, (_actual, example) in files.items()}
    base_expected = {
        (kind, key) for (kind, scope), keys in expected.items() if scope == "base" for key in keys
    }
    known_keys = {key for keys in expected.values() for key in keys}
    unknown = sorted(
        {key for values in source_values.values() for key in values if key not in known_keys}
    )
    if unknown and not drop_unknown:
        raise ValueError(f"unknown keys: {', '.join(unknown)}")

    values: dict[tuple[str, str], str] = {}
    all_sources = list(source_values.items())
    base_sources = [item for item in all_sources if item[0][1] == "base"]
    for identity, keys in expected.items():
        kind, scope = identity
        for key in keys:
            value: str | None
            if key == "ENVIRONMENT" and scope in RUNTIME_NAMES:
                value = RUNTIME_NAMES[scope]
            elif scope == "base":
                value = _one_value(key, all_sources)
            else:
                environment_sources = [item for item in all_sources if item[0][1] == scope]
                value = _one_value(key, environment_sources)
                if not value:
                    inherited = _one_value(key, base_sources)
                    if inherited is not None and ((kind, key) in base_expected or scope == "prod"):
                        value = inherited
            if value is not None:
                values[(f"{identity[0]}/{scope}", key)] = value

    return {
        actual: _render(example, f"{kind}/{scope}", values)
        for (kind, scope), (actual, example) in files.items()
    }


def normalized_outputs(
    root: Path,
    target: str,
    *,
    drop_unknown: bool = False,
    from_stg: bool = False,
) -> dict[Path, str]:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    if from_stg and target != "dev":
        raise ValueError("--from-stg is only valid for target dev")
    if target == "gh":
        return _github_outputs(root, drop_unknown=drop_unknown)
    if drop_unknown:
        raise ValueError("--drop-unknown is only valid for target gh")
    return _runtime_outputs(root, target, from_stg=from_stg)


def _write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    parser.add_argument(
        "--drop-unknown",
        action="store_true",
        help="remove obsolete GitHub keys after taking a snapshot",
    )
    parser.add_argument(
        "--from-stg",
        action="store_true",
        help="overlay declared nonprod credentials from local staging GitHub env files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        unknown = github_unknown_keys(ROOT) if args.target == "gh" else []
        outputs = normalized_outputs(
            ROOT,
            args.target,
            drop_unknown=args.drop_unknown,
            from_stg=args.from_stg,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    changed = [
        path for path, content in outputs.items() if path.read_text(encoding="utf-8") != content
    ]
    if args.check:
        for path in changed:
            print(f"drift: {path.relative_to(ROOT)}")
        return int(bool(changed))
    for path in changed:
        _write_atomic(path, outputs[path])
        print(f"synced {path.relative_to(ROOT)}")
    if args.drop_unknown:
        for key in unknown:
            print(f"dropped obsolete key: {key}")
    if not changed:
        print(f"ok: {args.target} env files already match their examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
