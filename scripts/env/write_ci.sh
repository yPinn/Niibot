#!/usr/bin/env bash
# Write deploy env files from GitHub values and env.manifest.json.
#
# Required env:
#   SECRETS_JSON        toJSON(secrets)  — { "NAME": "value", ... }
#   VARS_JSON           toJSON(vars)     — { "NAME": "value", ... }
#   PROJECT_DIR         repo checkout on the runner (manifest + output root)
#   DEPLOY_ENVIRONMENT  "production" | "staging"  (fallback for ENVIRONMENT)
# DRY_RUN=1 prints unredacted values; use fake input only.
set -euo pipefail
umask 077

: "${SECRETS_JSON:?SECRETS_JSON is required (pass env: SECRETS_JSON: \${{ toJSON(secrets) }})}"
: "${VARS_JSON:?VARS_JSON is required (pass env: VARS_JSON: \${{ toJSON(vars) }})}"
: "${PROJECT_DIR:?PROJECT_DIR is required}"
: "${DEPLOY_ENVIRONMENT:?DEPLOY_ENVIRONMENT is required (production|staging)}"
DRY_RUN="${DRY_RUN:-}"

export SECRETS_JSON VARS_JSON PROJECT_DIR DEPLOY_ENVIRONMENT DRY_RUN

python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

project_dir = Path(os.environ["PROJECT_DIR"])
deploy_env = os.environ["DEPLOY_ENVIRONMENT"].strip()
dry_run = os.environ.get("DRY_RUN") == "1"

aliases = {"development": "dev", "staging": "stg", "production": "prod"}
try:
    env = aliases[deploy_env]
except KeyError:
    print(f"ERROR: unsupported DEPLOY_ENVIRONMENT={deploy_env!r}", file=sys.stderr)
    sys.exit(1)

manifest = json.loads((project_dir / "env.manifest.json").read_text(encoding="utf-8"))

# Trim upload newlines; embedded newlines remain invalid.
secrets = {
    k: str(v).strip("\r\n")
    for k, v in json.loads(os.environ["SECRETS_JSON"] or "{}").items()
}
gh_vars = {
    k: str(v).strip("\r\n")
    for k, v in json.loads(os.environ["VARS_JSON"] or "{}").items()
}

FILE_PATHS = {
    "root": f".env.{env}",
    "shared": f"backend/shared.{env}.env",
    "api": f"backend/api/.env.{env}",
    "twitch": f"backend/twitch/.env.{env}",
    "discord": f"backend/discord/.env.{env}",
}

# ── required secrets ────────────────────────────────────────────────────────
missing = [
    name
    for name in manifest.get("required_secrets", [])
    if not secrets.get(name, "").strip()
]
if missing:
    print(f"ERROR: missing required GitHub Secrets: {' '.join(missing)}", file=sys.stderr)
    print("Configure at: Settings -> Secrets and variables -> Actions", file=sys.stderr)
    sys.exit(1)

missing = [
    name
    for name in manifest.get("required_variables", [])
    if not gh_vars.get(name, "").strip()
]
if missing:
    print(f"ERROR: missing required GitHub Variables: {' '.join(missing)}", file=sys.stderr)
    print("Configure at: Settings -> Secrets and variables -> Actions", file=sys.stderr)
    sys.exit(1)

# ── derived values ──────────────────────────────────────────────────────────
db_url = "postgresql://{}:{}@postgres:5432/{}".format(
    quote(gh_vars.get("POSTGRES_USER", ""), safe=""),
    quote(secrets.get("POSTGRES_PASSWORD", ""), safe=""),
    quote(gh_vars.get("POSTGRES_DB", ""), safe=""),
)


def quote_env(value: str) -> str:
    """Use literal dotenv quoting so Compose cannot expand secret `$` values."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def resolve(key: str, spec: dict) -> str:
    source = spec["source"]
    if source == "derived:db_url":
        return db_url
    kind, _, name = source.partition(":")
    if kind == "secret":
        return secrets.get(name, "")
    # kind == "var"
    val = gh_vars.get(name, "")
    if val:
        return val
    if key == "ENVIRONMENT":
        return deploy_env
    return spec.get("default", "")


# ── files ───────────────────────────────────────────────────────────────────
buffers: dict[str, list[str]] = {}
for key, spec in manifest["ci"].items():
    tag = spec.get("file")
    if not tag:  # runner-only
        continue
    if tag not in FILE_PATHS:
        print(f"ERROR: manifest ci[{key}].file={tag!r} has no known path", file=sys.stderr)
        sys.exit(1)
    value = resolve(key, spec)
    if spec.get("conditional") and not value:
        continue
    if "\n" in value or "\r" in value:
        print(f"ERROR: value for {key} contains a newline — refusing to write", file=sys.stderr)
        sys.exit(1)
    buffers.setdefault(tag, []).append(f"{key}={quote_env(value)}")

# Compose requires each declared env_file, including an empty optional file.
for tag, path_rel in FILE_PATHS.items():
    lines = buffers.get(tag, [])
    content = "".join(f"{line}\n" for line in lines)
    if dry_run:
        print(f"\n===== {path_rel} =====")
        print(content, end="")
        continue
    target = project_dir / path_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep LF output compatible with older runner Python versions.
    target.write_bytes(content.encode("utf-8"))
    print(f"wrote {path_rel} ({len(lines)} keys)")

if dry_run:
    print(f"\n(dry run - {env}, no files written)")
PYEOF
