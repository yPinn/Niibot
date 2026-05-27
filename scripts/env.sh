#!/usr/bin/env bash
# Copy all .env.example files to their .env counterparts.
# Skips files that already exist unless -f (force) is passed.

set -euo pipefail

FORCE=false
[[ "${1:-}" == "-f" ]] && FORCE=true

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

copy_env() {
  local src="$1"
  local dst="$2"

  if [[ -f "$dst" ]] && [[ "$FORCE" == false ]]; then
    echo "  skip   $dst (already exists; use -f to overwrite)"
    return
  fi

  cp "$src" "$dst"
  echo "  copied $dst"
}

echo "Initialising env files${FORCE:+ (force)}..."

copy_env "$ROOT/.env.example"                       "$ROOT/.env"
copy_env "$ROOT/backend/shared.env.example"         "$ROOT/backend/shared.env"
copy_env "$ROOT/backend/api/.env.example"           "$ROOT/backend/api/.env"
copy_env "$ROOT/backend/twitch/.env.example"        "$ROOT/backend/twitch/.env"
copy_env "$ROOT/backend/discord/.env.example"       "$ROOT/backend/discord/.env"
copy_env "$ROOT/backend/scrapling/.env.example"     "$ROOT/backend/scrapling/.env"
copy_env "$ROOT/frontend/.env.example"              "$ROOT/frontend/.env"

echo ""
echo "Done. Fill in secrets before running the project."
