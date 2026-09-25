#!/usr/bin/env bash
# Move legacy mutable files into the environment's runtime volume.
# Static backend/data content remains image-owned.
#
# Usage (run from project root):
#   bash backend/scripts/runtime/migrate.sh <legacy_dir> <runtime_dir>
#
#   prod: bash backend/scripts/runtime/migrate.sh backend/data backend/runtime
#   stg:  bash backend/scripts/runtime/migrate.sh data/staging/backend data/staging/runtime
#
# Safe to re-run: existing destinations are never overwritten.

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
