#!/usr/bin/env bash
# Pull current GitHub Variables to local files + report secret status.
# Variables (non-sensitive) are written to .github/variables/*.env.
# Secret values cannot be read via the API — only presence is reported.
#
# Usage:
#   bash .github/pull.sh prod
#   bash .github/pull.sh staging
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${1:-}"

if [[ -z "$ENV" || ( "$ENV" != "prod" && "$ENV" != "staging" ) ]]; then
  echo "Usage: bash .github/pull.sh [prod|staging]"
  exit 1
fi

GH_ENV="$( [[ "$ENV" == "prod" ]] && echo "production" || echo "staging" )"

# Resolve python binary — test actual execution to skip Windows Store aliases
PYTHON=""
for cmd in python3 python; do
  if "$cmd" -c "import sys" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
[[ -z "$PYTHON" ]] && { echo "ERROR: python not found (tried python3, python)"; exit 1; }

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
  printf '%s' "$json" > "$tmp"
  $PYTHON - "$tmp" "$outfile" "$example" <<'PYEOF'
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)
outfile      = sys.argv[2]
example_file = sys.argv[3] if len(sys.argv) > 3 else ""

if not data:
    print("  (none)")
    sys.exit(0)

vals       = {i["name"]: i["value"] for i in data}
file_lines = []
used_ex    = False

if example_file:
    sections = []
    cur_hdr, cur_hdr_line, cur_keys = None, None, []
    try:
        with open(example_file, encoding="utf-8") as ef:
            for line in ef:
                s        = line.rstrip("\n\r")
                stripped = s.strip()
                if stripped.startswith("# ──") or stripped.startswith("#──"):
                    if cur_hdr is not None or cur_keys:
                        sections.append((cur_hdr, cur_hdr_line, cur_keys))
                    cur_hdr      = stripped.strip("#─ ").strip()
                    cur_hdr_line = s
                    cur_keys     = []
                elif "=" in stripped and not stripped.startswith("#"):
                    k = stripped.split("=", 1)[0].strip()
                    if k:
                        cur_keys.append(k)
        if cur_hdr is not None or cur_keys:
            sections.append((cur_hdr, cur_hdr_line, cur_keys))
    except FileNotFoundError:
        sections = []

    if sections:
        all_ex   = [k for _, _, ks in sections for k in ks]
        extra_ks = [k for k in vals if k not in set(all_ex)]
        all_disp = [k for k in all_ex if k in vals and vals[k]] + [k for k in extra_ks if vals[k]]
        w        = max((len(k) for k in all_disp), default=0)
        first    = True
        for hdr, hdr_line, keys in sections:
            sec_all  = [(k, vals[k]) for k in keys if k in vals]
            sec_show = [(k, v) for k, v in sec_all if v]
            if not sec_all:
                continue
            if not first:
                file_lines.append("")
            first = False
            file_lines.append(hdr_line)
            for k, v in sec_all:
                file_lines.append(f"{k}={v}")
            if sec_show:
                print(f"  ── {hdr}")
                for k, v in sec_show:
                    print(f"    {k:<{w}}  {v}")
        if extra_ks:
            if not first:
                file_lines.append("")
            file_lines.append("# ── extra")
            show = [(k, vals[k]) for k in sorted(extra_ks) if vals[k]]
            if show:
                print("  ── extra")
                for k, v in show:
                    print(f"    {k:<{w}}  {v}")
            for k in sorted(extra_ks):
                file_lines.append(f"{k}={vals[k]}")
        used_ex = True

if not used_ex:
    data.sort(key=lambda x: x["name"])
    w = max((len(i["name"]) for i in data if i["value"]), default=0)
    for i in data:
        file_lines.append(f"{i['name']}={i['value']}")
        if i["value"]:
            print(f"  {i['name']:<{w}}  {i['value']}")

with open(outfile, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(file_lines) + "\n")
PYEOF
  rm -f "$tmp"
}

# Display secret status grouped by: set/env, base, miss
# Usage: show_secrets <env_json> <base_json> <example_file> <set_label>
show_secrets() {
  local env_json="$1" base_json="$2" example_file="$3" set_label="${4:-env}"
  local expected_keys
  expected_keys=$(grep -E '^[A-Z_]+=' "$example_file" | sed 's/=.*//' | tr '\n' ' ' || true)

  local tmp; tmp=$(mktemp)
  printf '%s\n%s\n%s\n%s\n' "$set_label" "$expected_keys" "$env_json" "$base_json" > "$tmp"
  $PYTHON - "$tmp" <<'PYEOF'
import json, sys, textwrap

with open(sys.argv[1]) as f:
    lines = f.read().split("\n", 3)
label   = lines[0].strip()
keys    = lines[1].split()
env_set = {i["name"] for i in json.loads(lines[2])}
base_set= {i["name"] for i in json.loads(lines[3])}

groups  = {label: [], "base": [], "miss": []}
for k in keys:
    if k in env_set:        groups[label].append(k)
    elif k in base_set:     groups["base"].append(k)
    else:                   groups["miss"].append(k)

extra = [n for n in env_set if n not in keys]

order = [label] + (["base"] if label != "base" else []) + ["miss"]
for g in order:
    items = groups.get(g, [])
    if not items:
        continue
    row     = "  ".join(items)
    wrapped = textwrap.wrap(row, width=60)
    pad     = f"  {g:<5} "
    cont    = " " * len(pad)
    for idx, part in enumerate(wrapped):
        print((pad if idx == 0 else cont) + part)

for name in extra:
    print(f"  extra {name}")
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
printf "%s  →  .github/variables/%s.env\n" "$ENV" "$ENV"
show_vars "$ENV_VARS_JSON" "$SCRIPT_DIR/variables/$ENV.env" "$SCRIPT_DIR/variables/$ENV.env.example"

printf "\n── secrets ─────────────────────────────────────────────\n\n"
printf "base\n"
show_secrets "$BASE_SECRETS_JSON" "[]" "$SCRIPT_DIR/secrets/base.env.example" "set"
printf "\n"
printf "%s\n" "$ENV"
show_secrets "$ENV_SECRETS_JSON" "$BASE_SECRETS_JSON" "$SCRIPT_DIR/secrets/$ENV.env.example" "env"
printf "\n"

printf "→  https://github.com/%s/settings/secrets/actions\n" "$REPO"
