#!/usr/bin/env bash
# Pull current GitHub Variables to local files + report secret status.
# Variables (non-sensitive) are written to .github/variables/*.env.
# Secret values cannot be read via the API — only presence is reported.
#
# Usage:
#   bash .github/pull.sh prod
#   bash .github/pull.sh stg
set -euo pipefail
umask 077
export PYTHONUTF8=1

TEMP_FILES=()
trap 'rm -f -- "${TEMP_FILES[@]}"' EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" || ( "$TARGET" != "prod" && "$TARGET" != "stg" ) ]]; then
  echo "Usage: bash .github/pull.sh [prod|stg]"
  exit 1
fi

GH_ENV="$( [[ "$TARGET" == "prod" ]] && echo "production" || echo "staging" )"

# Resolve python binary — test actual execution to skip Windows Store aliases
PYTHON=""
for cmd in python3 python; do
  if "$cmd" -c "import sys" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
[[ -z "$PYTHON" ]] && { echo "ERROR: python not found (tried python3, python)"; exit 1; }
"$PYTHON" "$SCRIPT_DIR/../scripts/env/gen.py" --check >/dev/null

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found  (brew install gh | winget install GitHub.cli)"
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
  echo "ERROR: not authenticated or not in a GitHub repo  (gh auth login)"
  exit 1
}

printf "%s  →  %s\n\n" "$REPO" "$GH_ENV"

# Display variables aligned (KEY  value) and write KEY=value to outfile
# Sections are read from example_file when provided.
# Usage: show_vars <json> <outfile> [example_file]
show_vars() {
  local json="$1" outfile="$2" example="${3:-}"
  local tmp; tmp=$(mktemp)
  TEMP_FILES+=("$tmp")
  printf '%s' "$json" > "$tmp"
  $PYTHON - "$tmp" "$outfile" "$example" <<'PYEOF'
import json, re, sys, textwrap

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
outfile      = sys.argv[2]
example_file = sys.argv[3] if len(sys.argv) > 3 else ""

vals       = {i["name"]: i["value"] for i in data}
file_lines = []
used_ex    = False

bad = [key for key, value in vals.items() if "\n" in value or "\r" in value]
if bad:
    print(f"ERROR: multiline GitHub Variables are not supported: {' '.join(bad)}", file=sys.stderr)
    sys.exit(1)

if example_file:
    try:
        with open(example_file, encoding="utf-8") as ef:
            example_lines = ef.read().splitlines()
    except FileNotFoundError:
        example_lines = []

    if example_lines:
        assignment = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")
        all_ex, required_ex, groups, current = [], [], {}, "variables"
        for line in example_lines:
            stripped = line.strip()
            if stripped.startswith("# ──") or stripped.startswith("#──"):
                current = stripped.strip("#─ ").strip()
            match = assignment.match(stripped)
            if match:
                key = match.group(2)
                all_ex.append(key)
                if match.group(1) is None:
                    required_ex.append(key)
                value = vals.get(key, "")
                file_lines.append(f"{key}={value}" if key in vals else line)
                if value:
                    groups.setdefault(current, []).append((key, value))
                continue
            file_lines.append(line)

        extra_ks = sorted(k for k in vals if k not in set(all_ex))
        all_disp = [k for k in all_ex if vals.get(k)] + [k for k in extra_ks if vals[k]]
        width = max((len(k) for k in all_disp), default=0)
        for header, items in groups.items():
            print(f"  ── {header}")
            for key, value in items:
                print(f"    {key:<{width}}  {value}")
        if extra_ks:
            if file_lines and file_lines[-1]:
                file_lines.append("")
            file_lines.append("# ── extra")
            show = [(k, vals[k]) for k in extra_ks if vals[k]]
            if show:
                print("  ── extra")
                for k, v in show:
                    print(f"    {k:<{width}}  {v}")
            for k in extra_ks:
                file_lines.append(f"{k}={vals[k]}")

        missing = [key for key in required_ex if key not in vals]
        if missing:
            wrapped = textwrap.wrap("  ".join(missing), width=60)
            for index, part in enumerate(wrapped):
                print(("  miss  " if index == 0 else " " * 8) + part)
        used_ex = True

if not used_ex:
    data.sort(key=lambda x: x["name"])
    w = max((len(i["name"]) for i in data if i["value"]), default=0)
    for i in data:
        file_lines.append(f"{i['name']}={i['value']}")
        if i["value"]:
            print(f"  {i['name']:<{w}}  {i['value']}")

if not data:
    print("  (none)")

with open(outfile, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(file_lines) + "\n")
PYEOF
  rm -f "$tmp"
}

# Report missing, inherited, and unexpected secret names without reading values.
# Usage: show_secrets <env_json> <base_json> <example_file>
show_secrets() {
  local env_json="$1" base_json="$2" example_file="$3"
  local tmp; tmp=$(mktemp)
  TEMP_FILES+=("$tmp")
  printf '%s\n%s\n' "$env_json" "$base_json" > "$tmp"
  $PYTHON - "$tmp" "$example_file" <<'PYEOF'
import json, re, sys, textwrap

with open(sys.argv[1], encoding="utf-8") as f:
    env_set  = {i["name"] for i in json.loads(f.readline())}
    base_set = {i["name"] for i in json.loads(f.readline())}

assignment = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")
keys, required = [], []
with open(sys.argv[2], encoding="utf-8") as f:
    for line in f:
        match = assignment.match(line.strip())
        if not match:
            continue
        keys.append(match.group(2))
        if match.group(1) is None:
            required.append(match.group(2))

expected  = set(keys)
missing   = [k for k in required if k not in env_set and k not in base_set]
inherited = [k for k in required if k not in env_set and k in base_set]
extra     = sorted(env_set - expected)

if not missing and not inherited and not extra:
    print("  all set")
else:
    for label, names in (("miss", missing), ("base-only", inherited), ("extra", extra)):
        if not names:
            continue
        wrapped = textwrap.wrap("  ".join(names), width=60)
        pad = f"  {label}  "
        for idx, part in enumerate(wrapped):
            print((pad if idx == 0 else " " * len(pad)) + part)
PYEOF
  rm -f "$tmp"
}

# Fetch all data first
BASE_VARS_JSON=$(gh variable list --repo "$REPO" --json name,value 2>/dev/null || echo "[]")
BASE_SECRETS_JSON=$(gh secret list --repo "$REPO" --json name 2>/dev/null || echo "[]")
ENV_VARS_JSON=$(gh variable list --repo "$REPO" --env "$GH_ENV" --json name,value 2>/dev/null || echo "[]")
ENV_SECRETS_JSON=$(gh secret list --repo "$REPO" --env "$GH_ENV" --json name 2>/dev/null || echo "[]")

printf "── variables ───────────────────────────────────────────\n\n"
printf "base  →  .github/variables/base.env\n"
show_vars "$BASE_VARS_JSON" "$SCRIPT_DIR/variables/base.env" "$SCRIPT_DIR/variables/base.env.example"
printf "\n"
printf "%s  →  .github/variables/%s.env\n" "$TARGET" "$TARGET"
show_vars "$ENV_VARS_JSON" "$SCRIPT_DIR/variables/$TARGET.env" "$SCRIPT_DIR/variables/$TARGET.env.example"

printf "\n── secrets ─────────────────────────────────────────────\n\n"
printf "base\n"
show_secrets "$BASE_SECRETS_JSON" "[]" "$SCRIPT_DIR/secrets/base.env.example"
printf "\n"
printf "%s\n" "$TARGET"
show_secrets "$ENV_SECRETS_JSON" "$BASE_SECRETS_JSON" "$SCRIPT_DIR/secrets/$TARGET.env.example"
printf "\n"

printf "→  https://github.com/%s/settings/secrets/actions\n" "$REPO"
