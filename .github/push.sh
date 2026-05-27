#!/usr/bin/env bash
# Push GitHub Secrets and Variables for the given environment.
# Base (repo-level) is always uploaded first, then environment overrides.
#
# Usage:
#   bash .github/push.sh prod
#   bash .github/push.sh staging
#
# Setup (one time):
#   brew install gh            # macOS
#   winget install GitHub.cli  # Windows
#   gh auth login
#
# Working files (copy from .env.example, fill in, never commit):
#   .github/secrets/base.env      .github/variables/base.env
#   .github/secrets/prod.env      .github/variables/prod.env
#   .github/secrets/staging.env   .github/variables/staging.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV="${1:-}"

if [[ -z "$ENV" || ( "$ENV" != "prod" && "$ENV" != "staging" ) ]]; then
  echo "ERROR: Environment required. Use: prod | staging"
  echo "Usage: bash .github/push.sh [prod|staging]"
  exit 1
fi

GH_ENV="$( [[ "$ENV" == "prod" ]] && echo "production" || echo "staging" )"

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install: brew install gh  |  winget install GitHub.cli"
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
  echo "ERROR: Not authenticated or not inside a GitHub repo. Run: gh auth login"
  exit 1
}

echo "Repository: $REPO"
echo "Environment: $ENV → GitHub Environment '$GH_ENV'"
echo ""

upload_secrets() {
  local file="$1" env_flag="${2:-}"
  if [[ -f "$file" ]]; then
    echo "Secrets: .github/secrets/$(basename "$file") ..."
    gh secret set --env-file "$file" --repo "$REPO" $env_flag
  else
    echo "WARN: $file not found — copy .github/secrets/$(basename "$file").example and fill in"
  fi
}

upload_vars() {
  local file="$1" env_flag="${2:-}"
  if [[ -f "$file" ]]; then
    echo "Variables: .github/variables/$(basename "$file") ..."
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
      [[ -z "${key// }" || "${key:0:1}" == "#" ]] && continue
      [[ -z "${value// }" ]] && continue
      gh variable set "$key" --body "$value" --repo "$REPO" $env_flag
      echo "  $key"
    done < "$file"
  else
    echo "WARN: $file not found — copy .github/variables/$(basename "$file").example and fill in"
  fi
}

# ── Base (repo-level) ─────────────────────────────────────────────────────────
echo "=== base ==="
upload_secrets "$SCRIPT_DIR/secrets/base.env"
upload_vars    "$SCRIPT_DIR/variables/base.env"
echo ""

# ── Environment overrides ─────────────────────────────────────────────────────
echo "=== $ENV ==="
upload_secrets "$SCRIPT_DIR/secrets/$ENV.env"  "--env $GH_ENV"
upload_vars    "$SCRIPT_DIR/variables/$ENV.env" "--env $GH_ENV"
echo ""

echo "Done. Verify at: https://github.com/$REPO/settings/secrets/actions"
