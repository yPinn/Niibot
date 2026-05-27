#!/usr/bin/env bash
# Show current GitHub Secrets (names only) and Variables (names + values).
# Secret values cannot be read back via the API — only their presence is confirmed.
#
# Usage:
#   bash .github/status.sh prod
#   bash .github/status.sh staging
set -euo pipefail

ENV="${1:-}"

if [[ -z "$ENV" || ( "$ENV" != "prod" && "$ENV" != "staging" ) ]]; then
  echo "ERROR: Environment required. Use: prod | staging"
  echo "Usage: bash .github/status.sh [prod|staging]"
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

# ── Base (repo-level) ─────────────────────────────────────────────────────────
echo "=== base secrets (names only) ==="
gh secret list --repo "$REPO" 2>/dev/null || echo "  (none)"
echo ""

echo "=== base variables ==="
gh variable list --repo "$REPO" 2>/dev/null || echo "  (none)"
echo ""

# ── Environment overrides ─────────────────────────────────────────────────────
echo "=== $ENV secrets (names only) ==="
gh secret list --repo "$REPO" --env "$GH_ENV" 2>/dev/null || echo "  (none)"
echo ""

echo "=== $ENV variables ==="
gh variable list --repo "$REPO" --env "$GH_ENV" 2>/dev/null || echo "  (none)"
echo ""

echo "Manage at: https://github.com/$REPO/settings/secrets/actions"
