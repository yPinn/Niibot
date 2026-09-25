#!/usr/bin/env python3
"""Validate an env file against its generated example without reading values aloud."""

from __future__ import annotations

import json
import posixpath
import re
import sys
import tomllib
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from urllib.parse import unquote, urlsplit

ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")
ROOT = Path(__file__).resolve().parents[2]
TARGETS = ("dev", "stg", "prod", "gh-stg", "gh-prod")
APPLICATION_IDENTITY_KEYS = {
    "BOT_ID",
    "DISCORD_PUBLIC_KEY",
    "NIGHTBOT_CLIENT_ID",
    "TWITCH_CLIENT_ID",
}


def keys(path: Path) -> list[str]:
    found: list[str] = []
    active: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = ASSIGNMENT.match(line.strip())
        if not match:
            continue
        commented, key, _value = match.groups()
        if key in active and commented is None:
            raise ValueError(f"{path}: duplicate {key} at line {line_no}")
        if key not in found:
            found.append(key)
        if commented is None:
            active.add(key)
    return found


def active_values(path: Path) -> dict[str, str]:
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


def _has_value(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    return bool(stripped and stripped not in {"''", '""'})


def _semantic_value(value: str | None) -> str:
    if value is None:
        return ""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _is_fernet_key(value: str) -> bool:
    try:
        return len(b64decode(value.strip().encode("ascii"), altchars=b"-_", validate=True)) == 32
    except (Base64Error, UnicodeEncodeError, ValueError):
        return False


def _registry(root: Path) -> list[dict]:
    data = tomllib.loads((root / "env.registry.toml").read_text(encoding="utf-8"))
    return list(data.get("var", []))


def _nonprod_shared_keys(root: Path) -> set[str]:
    return {
        variable.get("name", variable["key"])
        for variable in _registry(root)
        if variable.get("nonprod_shared")
    }


def _target_values(root: Path, target: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for path, _example in target_pairs(root, target):
        if path.is_file():
            values.update(active_values(path))
    return values


def value_errors(root: Path, target: str) -> list[str]:
    """Validate non-empty requirements and all-or-none groups without exposing values."""
    variables = _registry(root)
    values = _target_values(root, target)
    errors: list[str] = []

    if target.startswith("gh-") or target in {"dev", "stg", "prod"}:
        for variable in variables:
            ci = variable.get("ci", {})
            applies = bool(ci) if target.startswith("gh-") else bool(variable.get("scopes"))
            if variable.get("required") and applies:
                key = variable.get("name", variable["key"])
                if not _has_value(values.get(key)):
                    errors.append(f"required value is blank: {key}")
            key = variable.get("name", variable["key"])
            value = values.get(key)
            if variable.get("format") == "fernet" and _has_value(value):
                if not _is_fernet_key(value or ""):
                    errors.append(f"invalid Fernet key: {key}")

    groups: dict[str, list[dict]] = {}
    for variable in variables:
        if variable.get("group"):
            groups.setdefault(variable["group"], []).append(variable)

    for name, members in groups.items():
        if target.startswith("gh-"):
            members = [member for member in members if member.get("ci")]
        else:
            members = [member for member in members if member.get("scopes")]
        activators = [
            member.get("name", member["key"]) for member in members if member.get("activates_group")
        ]
        if not any(_has_value(values.get(key)) for key in activators):
            continue
        missing: list[str] = []
        for member in members:
            key = member.get("name", member["key"])
            has_default = target.startswith("gh-") and bool(member.get("default"))
            if not _has_value(values.get(key)) and not has_default:
                missing.append(key)
        if missing:
            errors.append(f"incomplete group {name}: missing {', '.join(missing)}")
    return errors


def deployment_path_errors(root: Path) -> list[str]:
    """Keep long-lived staging and production checkouts isolated."""
    paths: dict[str, str] = {}
    for scope in ("stg", "prod"):
        path = root / f".github/variables/{scope}.env"
        if not path.is_file():
            continue
        value = _semantic_value(active_values(path).get("PROJECT_DIR"))
        if value:
            paths[scope] = posixpath.normpath(value).casefold()

    if paths.get("stg") == paths.get("prod") and "stg" in paths:
        return ["staging and production PROJECT_DIR must differ"]
    return []


def dev_boundary_errors(root: Path) -> list[str]:
    """Keep dev internals isolated while allowing declared staging identities."""
    values = _target_values(root, "dev")
    nonprod_shared = _nonprod_shared_keys(root)
    errors: list[str] = []

    def database_parts(raw: str) -> tuple[str | None, str, str, str]:
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return None, "", "", ""
        return (
            parsed.hostname,
            unquote(parsed.username or ""),
            unquote(parsed.password or ""),
            unquote(parsed.path.lstrip("/")),
        )

    database_url = _semantic_value(values.get("DATABASE_URL"))
    database = database_parts(database_url) if database_url else None
    if database and database[0] not in {"localhost", "127.0.0.1", "::1"}:
        errors.append("dev DATABASE_URL must use a loopback host")

    docker_url = _semantic_value(values.get("DOCKER_DATABASE_URL"))
    docker_database = database_parts(docker_url) if docker_url else None
    if docker_database and docker_database[0] != "postgres":
        errors.append("dev DOCKER_DATABASE_URL must use postgres host")

    expected_database = tuple(
        _semantic_value(values.get(key))
        for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    )
    if all(expected_database):
        if database and database[1:] != expected_database:
            errors.append("dev DATABASE_URL must match POSTGRES_* credentials")
        if docker_database and docker_database[1:] != expected_database:
            errors.append("dev DOCKER_DATABASE_URL must match POSTGRES_* credentials")

    sensitive = {
        variable.get("name", variable["key"]): bool(variable.get("sensitive", True))
        for variable in _registry(root)
    }
    for scope in ("stg", "prod"):
        variable_path = root / f".github/variables/{scope}.env"
        if variable_path.is_file():
            deployed = active_values(variable_path)
            for key in sorted(APPLICATION_IDENTITY_KEYS & values.keys() & deployed.keys()):
                local_value = _semantic_value(values[key])
                if local_value and local_value == _semantic_value(deployed[key]):
                    if scope == "stg" and key in nonprod_shared:
                        continue
                    errors.append(f"dev value reuses {scope} application identity: {key}")

        secret_path = root / f".github/secrets/{scope}.env"
        if secret_path.is_file():
            deployed = active_values(secret_path)
            for key in sorted(values.keys() & deployed.keys()):
                if not sensitive.get(key, True):
                    continue
                local_value = _semantic_value(values[key])
                if local_value and local_value == _semantic_value(deployed[key]):
                    if scope == "stg" and key in nonprod_shared:
                        continue
                    errors.append(f"dev value reuses {scope} secret: {key}")

    return sorted(errors)


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
        return Path("frontend/.env.dev") if env == "dev" else None
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
    if not errors:
        errors.extend(value_errors(root, target))
        if target == "dev":
            errors.extend(dev_boundary_errors(root))
        elif target.startswith("gh-"):
            errors.extend(deployment_path_errors(root))
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
