#!/usr/bin/env python3
"""Initialize generated env files without rotating stored-credential keys."""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import secrets
import sys
import tempfile
from pathlib import Path

_TOKEN_KEY = "TWITCH_TOKEN_ENCRYPTION_KEY"
_ENVIRONMENTS = ("development", "staging", "production")


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _assign(path: Path, key: str, value: str, *, required: bool) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) > 1:
        raise ValueError(f"{key} is assigned more than once")
    if not matches:
        if required:
            raise ValueError(f"{key} assignment is missing")
        return False
    lines[matches[0]] = f"{prefix}{value}"
    _write_atomic(path, "\n".join(lines) + "\n")
    return True


def _validate_fernet_key(value: str) -> None:
    try:
        decoded = base64.b64decode(value.encode(), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{_TOKEN_KEY} is not a valid Fernet key") from exc
    if len(decoded) != 32:
        raise ValueError(f"{_TOKEN_KEY} is not a valid Fernet key")


def ensure_twitch_token_encryption_key(env_file: Path) -> bool:
    """Generate the local Fernet key only when absent or blank."""
    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines = content.splitlines()
    prefix = f"{_TOKEN_KEY}="
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) > 1:
        raise ValueError(f"{_TOKEN_KEY} is assigned more than once")

    if matches:
        existing = lines[matches[0]].removeprefix(prefix).strip()
        if existing:
            _validate_fernet_key(existing)
            return False

    generated = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    assignment = f"{prefix}{generated}"
    if matches:
        lines[matches[0]] = assignment
    else:
        lines.append(assignment)
    _write_atomic(env_file, "\n".join(lines) + "\n")
    return True


def refresh_shared_env_preserving_key(example_file: Path, env_file: Path) -> None:
    """Refresh from the example while retaining a valid existing key."""
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    prefix = f"{_TOKEN_KEY}="
    values = [
        line.removeprefix(prefix).strip()
        for line in existing.splitlines()
        if line.startswith(prefix)
    ]
    if len(values) > 1:
        raise ValueError(f"{_TOKEN_KEY} is assigned more than once")
    if values and values[0]:
        _validate_fernet_key(values[0])

    lines = example_file.read_text(encoding="utf-8").splitlines()
    indexes = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(indexes) != 1:
        raise ValueError(f"example must assign {_TOKEN_KEY} exactly once")
    if values and values[0]:
        lines[indexes[0]] = f"{prefix}{values[0]}"
    _write_atomic(env_file, "\n".join(lines) + "\n")


def set_environment(env_file: Path, environment: str) -> bool:
    if environment not in _ENVIRONMENTS:
        raise ValueError(f"unsupported environment {environment!r}")
    return _assign(env_file, "ENVIRONMENT", environment, required=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", type=Path)
    parser.add_argument("--refresh-from", type=Path, metavar="EXAMPLE")
    parser.add_argument("--environment", choices=_ENVIRONMENTS)
    parser.add_argument("--ensure-key", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.refresh_from is not None:
            refresh_shared_env_preserving_key(args.refresh_from, args.env_file)
        if args.environment is not None:
            set_environment(args.env_file, args.environment)
        if args.ensure_key:
            ensure_twitch_token_encryption_key(args.env_file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
