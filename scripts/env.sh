#!/usr/bin/env bash
# Unified env file manager.
#
# Usage: bash scripts/env.sh <command> [options]
#
#   init      [-f]              Copy .env.example → .env  (skip existing; -f overwrites)
#   snapshot  [--keep N]        Snapshot live env files to data/env/YYYYMMDD/
#   backup    [--keep N]        Snapshot + compress to data/secrets-YYYYMMDD.tar.gz
#   restore   <DATE|FILE> [-f]  Restore from snapshot or .tar.gz  (-f overwrites)
#   diff      [DATE|FILE]       Diff current env files against a snapshot
#   list                        List available snapshots and backups
#   clean     [--keep N]        Delete old snapshots/backups (default: keep 3)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data"

CMD="${1:-}"
shift 2>/dev/null || true

# ── File registry ─────────────────────────────────────────────────────────────
LOCAL_FILES=(
  ".env"
  "backend/shared.env"
  "backend/api/.env"
  "backend/discord/.env"
  "backend/twitch/.env"
  "backend/scrapling/.env"
  "frontend/.env"
)

CICD_FILES=(
  ".github/variables/base.env"
  ".github/variables/prod.env"
  ".github/variables/staging.env"
  ".github/secrets/base.env"
  ".github/secrets/prod.env"
  ".github/secrets/staging.env"
)

ALL_FILES=("${LOCAL_FILES[@]}" "${CICD_FILES[@]}")

# ── Internal helpers ──────────────────────────────────────────────────────────
_list_snapshots() {
  [[ -d "$DATA/env" ]] && ls "$DATA/env" 2>/dev/null | sort -r || true
}

_list_backups() {
  if ls "$DATA"/secrets-*.tar.gz &>/dev/null 2>&1; then
    ls "$DATA"/secrets-*.tar.gz | sort -r | while IFS= read -r f; do basename "$f"; done
  fi
}

_resolve_snap() {
  local arg="$1"
  if [[ "$arg" == *.tar.gz ]]; then
    local date snap
    date="$(basename "$arg" .tar.gz | sed 's/^secrets-//')"
    snap="$DATA/env/$date"
    if [[ ! -d "$snap" ]]; then
      printf "Extracting %s → data/env/\n\n" "$(basename "$arg")"
      mkdir -p "$DATA/env"
      tar -xzf "$arg" -C "$DATA/env"
    fi
    echo "$snap"
  elif [[ "$arg" =~ ^[0-9]{8}$ ]]; then
    echo "$DATA/env/$arg"
  else
    echo "error: expected YYYYMMDD or path to secrets-YYYYMMDD.tar.gz" >&2
    exit 1
  fi
}

_prune_snapshots() {
  local keep="$1" count=0
  while IFS= read -r d; do
    count=$((count + 1))
    [[ $count -le $keep ]] && continue
    rm -rf "$DATA/env/$d"
    echo "  removed snapshot $d"
  done < <(_list_snapshots)
}

_prune_backups() {
  local keep="$1" count=0
  while IFS= read -r f; do
    count=$((count + 1))
    [[ $count -le $keep ]] && continue
    rm -f "$DATA/$f"
    echo "  removed $f"
  done < <(_list_backups)
}

# ── init ──────────────────────────────────────────────────────────────────────
cmd_init() {
  local force=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -f) force=true; shift ;;
      *)  echo "error: unknown option: $1" >&2; exit 1 ;;
    esac
  done

  echo "Initialising env files${force:+ (force)}..."

  _copy_example() {
    local rel="$1" src="$ROOT/$1.example" dst="$ROOT/$1"
    if [[ ! -f "$src" ]]; then
      echo "  -      $rel.example (not found)"; return
    fi
    if [[ -f "$dst" ]] && [[ "$force" == false ]]; then
      echo "  skip   $rel (exists; -f to overwrite)"; return
    fi
    cp "$src" "$dst"
    echo "  copied $rel"
  }

  printf "── Local ────────────────────────────────────────────────\n"
  for f in "${LOCAL_FILES[@]}"; do _copy_example "$f"; done
  printf "\n── CI/CD ────────────────────────────────────────────────\n"
  for f in "${CICD_FILES[@]}"; do _copy_example "$f"; done
  echo ""
  echo "Done. Fill in secrets before running the project."
}

# ── snapshot ──────────────────────────────────────────────────────────────────
cmd_snapshot() {
  local keep=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) keep="$2"; shift 2 ;;
      *)      echo "error: unknown option: $1" >&2; exit 1 ;;
    esac
  done

  local date snap copied=0 skipped=0
  date="$(date +%Y%m%d)"
  snap="$DATA/env/$date"
  mkdir -p "$snap"

  _cp_env() {
    local src="$ROOT/$1" dst="$snap/$1"
    mkdir -p "$(dirname "$dst")"
    if [[ -f "$src" ]]; then
      cp "$src" "$dst"; echo "  ✓  $1"; copied=$((copied + 1))
    else
      echo "  -  $1 (not found)"; skipped=$((skipped + 1))
    fi
  }

  printf "══ Snapshot  →  %s\n\n" "$snap"
  printf "── Local ────────────────────────────────────────────────\n"
  for f in "${LOCAL_FILES[@]}"; do _cp_env "$f"; done
  printf "\n── CI/CD ────────────────────────────────────────────────\n"
  for f in "${CICD_FILES[@]}"; do _cp_env "$f"; done
  printf "\n%d copied, %d skipped\n" "$copied" "$skipped"

  if [[ $keep -gt 0 ]]; then _prune_snapshots "$keep"; fi
}

# ── backup ────────────────────────────────────────────────────────────────────
cmd_backup() {
  local keep=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) keep="$2"; shift 2 ;;
      *)      echo "error: unknown option: $1" >&2; exit 1 ;;
    esac
  done

  cmd_snapshot  # creates data/env/YYYYMMDD/ and prints progress

  local date out
  date="$(date +%Y%m%d)"
  out="$DATA/secrets-$date.tar.gz"
  tar -czf "$out" -C "$DATA/env" "$date"
  echo "→ $out"

  if [[ $keep -gt 0 ]]; then
    _prune_snapshots "$keep"
    _prune_backups   "$keep"
  fi
}

# ── restore ───────────────────────────────────────────────────────────────────
cmd_restore() {
  local force=false arg=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -f) force=true; shift ;;
      *)  arg="$1"; shift ;;
    esac
  done

  if [[ -z "$arg" ]]; then cmd_list; exit 0; fi

  local snap
  snap="$(_resolve_snap "$arg")"
  [[ -d "$snap" ]] || { echo "error: snapshot not found: $snap" >&2; exit 1; }

  local copied=0 skipped=0

  _import_env() {
    local rel="$1" src="$snap/$1" dst="$ROOT/$1"
    if [[ ! -f "$src" ]]; then
      echo "  -  $rel (not in snapshot)"; skipped=$((skipped + 1)); return
    fi
    if [[ -f "$dst" ]] && [[ "$force" == false ]]; then
      echo "  skip  $rel (exists; -f to overwrite)"; skipped=$((skipped + 1)); return
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"; echo "  ✓  $rel"; copied=$((copied + 1))
  }

  printf "══ Restore  ←  %s\n\n" "$snap"
  printf "── Local ────────────────────────────────────────────────\n"
  for f in "${LOCAL_FILES[@]}"; do _import_env "$f"; done
  printf "\n── CI/CD ────────────────────────────────────────────────\n"
  for f in "${CICD_FILES[@]}"; do _import_env "$f"; done
  printf "\n%d restored, %d skipped\n" "$copied" "$skipped"
}

# ── diff ──────────────────────────────────────────────────────────────────────
cmd_diff() {
  local arg="${1:-}" snap

  if [[ -z "$arg" ]]; then
    local latest
    latest="$(_list_snapshots | head -1)"
    [[ -n "$latest" ]] || { echo "No snapshots available." >&2; exit 1; }
    snap="$DATA/env/$latest"
    echo "Comparing against: $latest"
  else
    snap="$(_resolve_snap "$arg")"
    [[ -d "$snap" ]] || { echo "error: snapshot not found: $snap" >&2; exit 1; }
  fi

  echo ""
  local changed=0 missing=0 same=0

  for rel in "${ALL_FILES[@]}"; do
    local cur="$ROOT/$rel" old="$snap/$rel"
    if [[ ! -f "$cur" && ! -f "$old" ]]; then
      continue
    elif [[ ! -f "$old" ]]; then
      echo "  + $rel  (new — not in snapshot)"
      changed=$((changed + 1))
    elif [[ ! -f "$cur" ]]; then
      echo "  ✗ $rel  (missing locally)"
      missing=$((missing + 1))
    elif ! diff -q "$cur" "$old" &>/dev/null; then
      echo "  ~ $rel"
      diff --unified=0 --label snapshot --label current "$old" "$cur" \
        | tail -n +3 | head -30 || true
      echo ""
      changed=$((changed + 1))
    else
      printf "    %s\n" "$rel"
      same=$((same + 1))
    fi
  done

  echo ""
  printf "%d changed  |  %d missing locally  |  %d unchanged\n" \
    "$changed" "$missing" "$same"
}

# ── list ──────────────────────────────────────────────────────────────────────
cmd_list() {
  local snaps backups
  snaps="$(_list_snapshots)"
  backups="$(_list_backups)"

  if [[ -n "$snaps" ]]; then
    echo "Snapshots  (data/env/):"
    echo "$snaps" | while IFS= read -r d; do echo "  $d"; done
    echo ""
  else
    echo "No snapshots found."; echo ""
  fi

  if [[ -n "$backups" ]]; then
    echo "Backups  (data/):"
    echo "$backups" | while IFS= read -r f; do echo "  $f"; done
  else
    echo "No backups found."
  fi
}

# ── clean ─────────────────────────────────────────────────────────────────────
cmd_clean() {
  local keep=3
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) keep="$2"; shift 2 ;;
      *)      echo "error: unknown option: $1" >&2; exit 1 ;;
    esac
  done

  echo "Keeping last $keep  (snapshots and backups)..."
  _prune_snapshots "$keep"
  _prune_backups   "$keep"
  echo "Done."
}

# ── router ────────────────────────────────────────────────────────────────────
case "$CMD" in
  init)     cmd_init     "$@" ;;
  snapshot) cmd_snapshot "$@" ;;
  backup)   cmd_backup   "$@" ;;
  restore)  cmd_restore  "$@" ;;
  diff)     cmd_diff     "$@" ;;
  list)     cmd_list ;;
  clean)    cmd_clean    "$@" ;;
  *)
    cat <<'EOF'
Usage: bash scripts/env.sh <command> [options]

  init      [-f]              Copy .env.example → .env  (skip existing; -f overwrites)
  snapshot  [--keep N]        Snapshot live env files to data/env/YYYYMMDD/
  backup    [--keep N]        Snapshot + compress to data/secrets-YYYYMMDD.tar.gz
  restore   <DATE|FILE> [-f]  Restore from snapshot or .tar.gz  (-f overwrites)
  diff      [DATE|FILE]       Diff current env files against a snapshot
  list                        List available snapshots and backups
  clean     [--keep N]        Delete old snapshots/backups (default: keep 3)
EOF
    ;;
esac
