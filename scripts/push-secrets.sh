#!/usr/bin/env bash
# Upload GitHub Secrets and Variables from local env files in one shot.
#
# Usage:
#   bash scripts/push-secrets.sh
#
# Setup (one time):
#   brew install gh          # macOS
#   winget install GitHub.cli  # Windows
#   gh auth login
#
# Then:
#   cp secrets.env.example secrets.env    # fill in values
#   cp variables.env.example variables.env  # adjust as needed
#   bash scripts/push-secrets.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SECRETS_FILE="$ROOT_DIR/secrets.env"
VARIABLES_FILE="$ROOT_DIR/variables.env"

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found."
  echo "  macOS:   brew install gh"
  echo "  Windows: winget install GitHub.cli"
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
  echo "ERROR: Not authenticated or not inside a GitHub repo. Run: gh auth login"
  exit 1
}

echo "Repository: $REPO"
echo ""

# ── Secrets ──────────────────────────────────────────────────────────────────
if [[ -f "$SECRETS_FILE" ]]; then
  echo "Uploading secrets from secrets.env ..."
  # gh secret set --env-file skips blank lines, comments, and empty values.
  gh secret set --env-file "$SECRETS_FILE" --repo "$REPO"
  echo "Secrets uploaded."
else
  echo "WARN: secrets.env not found — copy secrets.env.example and fill in values."
fi

echo ""

# ── Variables ─────────────────────────────────────────────────────────────────
if [[ -f "$VARIABLES_FILE" ]]; then
  echo "Uploading variables from variables.env ..."
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Skip blank lines and comments
    [[ -z "${key// }" || "${key:0:1}" == "#" ]] && continue
    # Skip empty values
    [[ -z "${value// }" ]] && continue
    gh variable set "$key" --body "$value" --repo "$REPO"
    echo "  VAR $key"
  done < "$VARIABLES_FILE"
  echo "Variables uploaded."
else
  echo "WARN: variables.env not found — copy variables.env.example and adjust values."
fi

echo ""
echo "Done. Verify at: https://github.com/$REPO/settings/secrets/actions"
