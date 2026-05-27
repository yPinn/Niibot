#!/usr/bin/env bash
# Push GitHub Secrets and Variables for the given environment.
# Base (repo-level) is uploaded first, then environment overrides.
# Empty values are skipped — they remain unset on GitHub.
#
# Usage:
#   bash .github/push.sh prod
#   bash .github/push.sh staging
#
# One-time setup:
#   brew install gh  |  winget install GitHub.cli
#   gh auth login
#
# Working files (copy from .example, fill in, never commit):
#   .github/secrets/base.env       .github/variables/base.env
#   .github/secrets/prod.env       .github/variables/prod.env
#   .github/secrets/staging.env    .github/variables/staging.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${1:-}"

if [[ -z "$ENV" || ( "$ENV" != "prod" && "$ENV" != "staging" ) ]]; then
  echo "Usage: bash .github/push.sh [prod|staging]"
  exit 1
fi

GH_ENV="$( [[ "$ENV" == "prod" ]] && echo "production" || echo "staging" )"

# Resolve python binary — test actual execution to skip Windows Store aliases
PYTHON=""
for cmd in python3 python; do
  if "$cmd" -c "import sys" 2>/dev/null; then PYTHON="$cmd"; break; fi
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

# Push secrets from file, skipping empty values
push_secrets() {
  local file="$1"; shift; local env_flags=("$@")
  local pushed=0 skipped=0

  if [[ ! -f "$file" ]]; then
    printf "  secrets   WARN: %s not found — copy from .example\n" "$(basename "$file")"
    return
  fi

  local tmp
  tmp=$(mktemp)
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    key="${key%$'\r'}"; value="${value%$'\r'}"   # strip Windows CRLF
    [[ -z "${key// }" || "${key:0:1}" == "#" ]] && continue
    if [[ -z "${value// }" ]]; then
      skipped=$((skipped + 1))
    else
      printf "%s=%s\n" "$key" "$value" >> "$tmp"
      pushed=$((pushed + 1))
    fi
  done < "$file"

  [[ -s "$tmp" ]] && gh secret set --env-file "$tmp" --repo "$REPO" "${env_flags[@]}" > /dev/null
  rm -f "$tmp"

  local summary="${pushed} pushed"
  [[ $pushed  -eq 0 ]] && summary="up to date"
  [[ $skipped -gt 0 ]] && summary+="  ($skipped empty)"
  printf "  secrets   %s\n" "$summary"
}

# Push variables from file, skipping empty and unchanged values
push_vars() {
  local file="$1"; shift; local env_flags=("${@}")
  local new_count=0 updated=0 unchanged=0 skipped=0
  local new_keys=() updated_keys=()

  if [[ ! -f "$file" ]]; then
    printf "  variables WARN: %s not found — copy from .example\n" "$(basename "$file")"
    return
  fi

  # Fetch current values from GitHub once
  local current_json
  current_json=$(gh variable list --repo "$REPO" ${env_flags[@]+"${env_flags[@]}"} --json name,value 2>/dev/null || echo "[]")
  local current_map
  current_map=$(printf '%s' "$current_json" | $PYTHON -c "
import json, sys
for i in json.load(sys.stdin.buffer): print(f\"{i['name']}={i['value']}\")
")

  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    key="${key%$'\r'}"; value="${value%$'\r'}"   # strip Windows CRLF
    [[ -z "${key// }" || "${key:0:1}" == "#" ]] && continue
    if [[ -z "${value// }" ]]; then
      skipped=$((skipped + 1)); continue
    fi
    local current_val
    current_val=$(printf '%s' "$current_map" | grep "^${key}=" | cut -d'=' -f2- || true)
    if [[ "$current_val" == "$value" ]]; then
      unchanged=$((unchanged + 1))
    elif [[ ! "$current_map" =~ (^|$'\n')"${key}=" ]]; then
      gh variable set "$key" --body "$value" --repo "$REPO" ${env_flags[@]+"${env_flags[@]}"} > /dev/null
      new_keys+=("$key"); new_count=$((new_count + 1))
    else
      gh variable set "$key" --body "$value" --repo "$REPO" ${env_flags[@]+"${env_flags[@]}"} > /dev/null
      updated_keys+=("$key"); updated=$((updated + 1))
    fi
  done < "$file"

  local summary="up to date"
  if [[ $new_count -gt 0 || $updated -gt 0 ]]; then
    summary=""
    [[ $new_count -gt 0 ]] && summary+="${new_count} new: ${new_keys[*]}"
    [[ $updated   -gt 0 ]] && summary+="${summary:+  }${updated} updated: ${updated_keys[*]}"
  fi
  [[ $skipped -gt 0 ]] && summary+="  ($skipped empty)"
  printf "  variables %s\n" "$summary"
}

printf "── variables ───────────────────────────────────────────\n\n"
printf "base\n"
push_vars "$SCRIPT_DIR/variables/base.env"
printf "\n"
printf "%s\n" "$ENV"
push_vars "$SCRIPT_DIR/variables/$ENV.env" --env "$GH_ENV"

printf "\n── secrets ─────────────────────────────────────────────\n\n"
printf "base\n"
push_secrets "$SCRIPT_DIR/secrets/base.env"
printf "\n"
printf "%s\n" "$ENV"
push_secrets "$SCRIPT_DIR/secrets/$ENV.env" --env "$GH_ENV"
printf "\n"

printf "→  https://github.com/%s/settings/secrets/actions\n" "$REPO"
