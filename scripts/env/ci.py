#!/usr/bin/env python3
"""Render deployment env files from GitHub Actions values."""

from __future__ import annotations

import json
import os
import sys
from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from urllib.parse import quote

ENV_ALIASES = {"development": "dev", "staging": "stg", "production": "prod"}


def _has_value(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    return bool(stripped and stripped not in {"''", '""'})


def _quote_env(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _is_fernet_key(value: str) -> bool:
    try:
        return len(b64decode(value.strip().encode("ascii"), altchars=b"-_", validate=True)) == 32
    except (Base64Error, UnicodeEncodeError, ValueError):
        return False


def render_files(
    manifest: dict,
    *,
    secrets: dict[str, str],
    variables: dict[str, str],
    deploy_environment: str,
) -> dict[str, str]:
    """Resolve and quote CI values without writing or logging credentials."""
    deploy_environment = deploy_environment.strip()
    try:
        env = ENV_ALIASES[deploy_environment]
    except KeyError as exc:
        raise ValueError(f"unsupported DEPLOY_ENVIRONMENT={deploy_environment!r}") from exc

    secrets = {key: str(value).strip("\r\n") for key, value in secrets.items()}
    variables = {key: str(value).strip("\r\n") for key, value in variables.items()}

    missing_secrets = [
        name for name in manifest.get("required_secrets", []) if not _has_value(secrets.get(name))
    ]
    if missing_secrets:
        raise ValueError(f"missing required GitHub Secrets: {' '.join(missing_secrets)}")
    missing_variables = [
        name
        for name in manifest.get("required_variables", [])
        if not _has_value(variables.get(name))
    ]
    if missing_variables:
        raise ValueError(f"missing required GitHub Variables: {' '.join(missing_variables)}")

    database_url = "postgresql://{}:{}@postgres:5432/{}".format(
        quote(variables.get("POSTGRES_USER", ""), safe=""),
        quote(secrets.get("POSTGRES_PASSWORD", ""), safe=""),
        quote(variables.get("POSTGRES_DB", ""), safe=""),
    )

    def raw_value(spec: dict) -> str:
        source = spec["source"]
        if source == "derived:db_url":
            return database_url
        kind, _, name = source.partition(":")
        return secrets.get(name, "") if kind == "secret" else variables.get(name, "")

    def resolved_value(key: str, spec: dict) -> str:
        value = raw_value(spec)
        if _has_value(value):
            return value
        if key == "ENVIRONMENT":
            return deploy_environment
        return spec.get("default", "")

    for key, spec in manifest["ci"].items():
        value = raw_value(spec)
        if spec.get("format") == "fernet" and _has_value(value):
            if not _is_fernet_key(value):
                raise ValueError(f"invalid Fernet key: {key}")

    inactive_members: set[str] = set()
    for name, group in manifest.get("ci_groups", {}).items():
        members = group.get("members", [])
        activators = group.get("activators", [])
        if not any(_has_value(raw_value(manifest["ci"][key])) for key in activators):
            inactive_members.update(members)
            continue
        missing = [
            key for key in members if not _has_value(resolved_value(key, manifest["ci"][key]))
        ]
        if missing:
            raise ValueError(f"incomplete group {name}: missing {', '.join(missing)}")

    file_paths = {
        "root": f".env.{env}",
        "shared": f"backend/shared.{env}.env",
        "api": f"backend/api/.env.{env}",
        "twitch": f"backend/twitch/.env.{env}",
        "discord": f"backend/discord/.env.{env}",
    }
    buffers: dict[str, list[str]] = {tag: [] for tag in file_paths}
    for key, spec in manifest["ci"].items():
        tag = spec.get("file")
        if not tag:
            continue
        if tag not in file_paths:
            raise ValueError(f"manifest ci[{key}].file={tag!r} has no known path")
        if key in inactive_members:
            continue
        value = resolved_value(key, spec)
        if spec.get("conditional") and not _has_value(value):
            continue
        if "\n" in value or "\r" in value:
            raise ValueError(f"value for {key} contains a newline")
        buffers[tag].append(f"{key}={_quote_env(value)}")

    return {
        file_paths[tag]: "".join(f"{line}\n" for line in lines) for tag, lines in buffers.items()
    }


def main() -> int:
    try:
        project_dir = Path(os.environ["PROJECT_DIR"])
        deploy_environment = os.environ["DEPLOY_ENVIRONMENT"]
        manifest = json.loads((project_dir / "env.manifest.json").read_text(encoding="utf-8"))
        secrets = json.loads(os.environ.get("SECRETS_JSON", "{}"))
        variables = json.loads(os.environ.get("VARS_JSON", "{}"))
        rendered = render_files(
            manifest,
            secrets=secrets,
            variables=variables,
            deploy_environment=deploy_environment,
        )
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    dry_run = os.environ.get("DRY_RUN") == "1"
    for relative, content in rendered.items():
        if dry_run:
            print(f"would write {relative} ({content.count(chr(10))} keys)")
            continue
        target = project_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        print(f"wrote {relative} ({content.count(chr(10))} keys)")
    if dry_run:
        print(f"dry run: {ENV_ALIASES[deploy_environment.strip()]}, no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
