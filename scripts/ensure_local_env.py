#!/usr/bin/env python3
"""Generate local-only env secrets that must exist before services start."""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import secrets
import sys
import tempfile
from pathlib import Path

_TWITCH_TOKEN_KEY = "TWITCH_TOKEN_ENCRYPTION_KEY"


def _validate_fernet_key(value: str) -> None:
    try:
        decoded = base64.b64decode(value.encode(), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{_TWITCH_TOKEN_KEY} is not a valid Fernet key") from exc
    if len(decoded) != 32:
        raise ValueError(f"{_TWITCH_TOKEN_KEY} is not a valid Fernet key")


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def ensure_twitch_token_encryption_key(env_file: Path) -> bool:
    """Set a local Fernet key only when its assignment is absent or blank."""
    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines = content.splitlines()
    prefix = f"{_TWITCH_TOKEN_KEY}="
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) > 1:
        raise ValueError(f"{_TWITCH_TOKEN_KEY} is assigned more than once")

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
    """Replace a shared env from its example without rotating a valid key."""
    existing_content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    prefix = f"{_TWITCH_TOKEN_KEY}="
    existing_values = [
        line.removeprefix(prefix).strip()
        for line in existing_content.splitlines()
        if line.startswith(prefix)
    ]
    if len(existing_values) > 1:
        raise ValueError(f"{_TWITCH_TOKEN_KEY} is assigned more than once")

    existing_key = existing_values[0] if existing_values else ""
    if existing_key:
        _validate_fernet_key(existing_key)

    example_lines = example_file.read_text(encoding="utf-8").splitlines()
    assignment_indexes = [
        index for index, line in enumerate(example_lines) if line.startswith(prefix)
    ]
    if len(assignment_indexes) != 1:
        raise ValueError(f"example must assign {_TWITCH_TOKEN_KEY} exactly once")
    if existing_key:
        example_lines[assignment_indexes[0]] = f"{prefix}{existing_key}"
    _write_atomic(env_file, "\n".join(example_lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", type=Path, help="local shared env file to update")
    parser.add_argument(
        "--refresh-from",
        type=Path,
        metavar="EXAMPLE_FILE",
        help="replace from an example while retaining the current encryption key",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.refresh_from is not None:
            refresh_shared_env_preserving_key(args.refresh_from, args.env_file)
        generated = ensure_twitch_token_encryption_key(args.env_file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    action = "generated" if generated else "kept"
    print(f"  {action} {_TWITCH_TOKEN_KEY} in backend/shared.env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
