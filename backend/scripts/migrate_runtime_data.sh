#!/usr/bin/env bash
# Idempotent migration: move mutable runtime files from legacy ./data/ to ./runtime/.
#
# Background:
#   Before this refactor, log_channels.json + active_giveaways.json lived in the
#   same dir as static repo content (backend/data/), forcing each env to mount
#   that whole dir as a volume. Static content (packs, embed.json, …)
#   is now baked into the image, and only runtime state lives in backend/runtime/.
#
# Usage (run from project root):
#   bash backend/scripts/migrate_runtime_data.sh <legacy_dir> <runtime_dir>
#
#   Prod:    bash backend/scripts/migrate_runtime_data.sh backend/data       backend/runtime
#   Staging: bash backend/scripts/migrate_runtime_data.sh data/staging/backend data/staging/runtime
#
# Safe to re-run: each move checks that source exists and dest doesn't.

set -euo pipefail

LEGACY_DIR="${1:?usage: $0 <legacy_dir> <runtime_dir>}"
RUNTIME_DIR="${2:?usage: $0 <legacy_dir> <runtime_dir>}"

mkdir -p "$RUNTIME_DIR"

# (src_filename, dst_filename) — dst may differ because we renamed active_giveaways → giveaway_state.
declare -a MOVES=(
    "log_channels.json:log_channels.json"
    "active_giveaways.json:giveaway_state.json"
)

for entry in "${MOVES[@]}"; do
    src_name="${entry%%:*}"
    dst_name="${entry##*:}"
    src="$LEGACY_DIR/$src_name"
    dst="$RUNTIME_DIR/$dst_name"

    if [ ! -f "$src" ]; then
        echo "[skip] $src not present"
        continue
    fi
    if [ -f "$dst" ]; then
        echo "[skip] $dst already exists — leaving $src untouched"
        continue
    fi
    mv "$src" "$dst"
    echo "[moved] $src -> $dst"
done

echo "Runtime data migration complete."
