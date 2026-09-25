#!/usr/bin/env bash
# Unified env file manager.
#
# Preferred: npm run nb -- env <command>
# Direct:    bash scripts/env/manage.sh <command> [options]
#
#   init      [dev|stg|prod] [-f]  Copy templates; defaults to dev
#   migrate   <dev|stg|prod>       Rename legacy env files; target is required
#   snapshot  [--keep N]        Snapshot live env files to data/env/YYYYMMDD/
#   backup    [--keep N]        Snapshot + compress to data/env-YYYYMMDD.tar.gz
#   restore   <DATE|FILE> [-f]  Restore from snapshot or .tar.gz  (-f overwrites)
#   diff      [DATE|FILE]       Diff current env files against a snapshot
#   list                        List available snapshots and backups
#   clean     [--keep N]        Delete old snapshots/backups (default: keep 3)
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="$ROOT/data"

CMD="${1:-}"
shift 2>/dev/null || true

# ── File registry ─────────────────────────────────────────────────────────────
_MANIFEST="$ROOT/env.manifest.json"
_PY=""
for _c in python3 python py; do
  if "$_c" -c "import sys" >/dev/null 2>&1; then _PY="$_c"; break; fi
done

TEMPLATE_FILES=()
if [[ -n "$_PY" && -f "$_MANIFEST" ]]; then
  while IFS= read -r file; do
    TEMPLATE_FILES+=("$file")
  done < <("$_PY" -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1]))['runtime_files']))" "$_MANIFEST" | tr -d '\r')
fi
if [[ ${#TEMPLATE_FILES[@]} -eq 0 ]]; then
  [[ -f "$_MANIFEST" ]] || echo "warning: $_MANIFEST missing — run 'npm run env:gen'" >&2
  TEMPLATE_FILES=(
    ".env" "backend/shared.env" "backend/api/.env" "backend/discord/.env"
    "backend/twitch/.env" "backend/scrapling/.env" "frontend/.env"
  )
fi

_env_path() {
  local template="$1" env="$2"
  case "$template" in
    frontend/*) if [[ "$env" == "dev" ]]; then echo "$template"; fi ;;
    .env) echo ".env.$env" ;;
    backend/shared.env) echo "backend/shared.$env.env" ;;
    *) echo "${template%.env}.env.$env" ;;
  esac
  return 0
}

DEV_FILES=(); STG_FILES=(); PROD_FILES=()
for f in "${TEMPLATE_FILES[@]}"; do
  value="$(_env_path "$f" dev)";  [[ -z "$value" ]] || DEV_FILES+=("$value")
  value="$(_env_path "$f" stg)";  [[ -z "$value" ]] || STG_FILES+=("$value")
  value="$(_env_path "$f" prod)"; [[ -z "$value" ]] || PROD_FILES+=("$value")
done

CICD_FILES=(
  ".github/variables/base.env"
  ".github/variables/prod.env"
  ".github/variables/stg.env"
  ".github/secrets/base.env"
  ".github/secrets/prod.env"
  ".github/secrets/stg.env"
)

ALL_FILES=("${DEV_FILES[@]}" "${STG_FILES[@]}" "${PROD_FILES[@]}" "${CICD_FILES[@]}")

# ── Internal helpers ──────────────────────────────────────────────────────────
_list_snapshots() {
  [[ -d "$DATA/env" ]] && ls "$DATA/env" 2>/dev/null | sort -r || true
}

_list_backups() {
  if ls "$DATA"/env-*.tar.gz &>/dev/null 2>&1; then
    ls "$DATA"/env-*.tar.gz | sort -r | while IFS= read -r f; do basename "$f"; done
  fi
}

_resolve_snap() {
  local arg="$1"
  if [[ "$arg" == *.tar.gz ]]; then
    local date snap
    date="$(basename "$arg" .tar.gz | sed 's/^env-//')"
    snap="$DATA/env/$date"
    if [[ ! -d "$snap" ]]; then
      printf "Extracting %s → data/env/\n\n" "$(basename "$arg")" >&2
      mkdir -p "$DATA/env"
      tar -xzf "$arg" -C "$DATA/env"
    fi
    echo "$snap"
  elif [[ "$arg" =~ ^[0-9]{8}$ ]]; then
    echo "$DATA/env/$arg"
  else
    echo "error: expected YYYYMMDD or path to env-YYYYMMDD.tar.gz" >&2
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

# Apply function $1 to every file, grouped under section headers.
_each_section() {
  local fn="$1"
  printf "── dev ──────────────────────────────────────────────────\n"
  for f in "${DEV_FILES[@]}"; do "$fn" "$f"; done
  printf "\n── stg ──────────────────────────────────────────────────\n"
  for f in "${STG_FILES[@]}"; do "$fn" "$f"; done
  printf "\n── prod ─────────────────────────────────────────────────\n"
  for f in "${PROD_FILES[@]}"; do "$fn" "$f"; done
  printf "\n── CI/CD ────────────────────────────────────────────────\n"
  for f in "${CICD_FILES[@]}";    do "$fn" "$f"; done
}

# ── init ──────────────────────────────────────────────────────────────────────
cmd_init() {
  local force=false env=dev
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -f) force=true; shift ;;
      dev|stg|prod) env="$1"; shift ;;
      *)  echo "error: unknown option: $1" >&2; exit 1 ;;
    esac
  done
  [[ -n "$_PY" ]] || { echo "error: Python is required for env init" >&2; exit 1; }

  local runtime suffix=""
  case "$env" in
    dev) runtime=development ;;
    stg) runtime=staging ;;
    prod) runtime=production ;;
  esac
  [[ "$force" == true ]] && suffix=" (force)"
  echo "Initialising $env env files$suffix..."

  _set_runtime() {
    local dst="$1"
    "$_PY" "$ROOT/scripts/env/init.py" "$dst" --environment "$runtime"
  }

  _copy_example() {
    local rel="$1" template src dst
    case "$rel" in
      .env.*) template=".env" ;;
      backend/shared.*.env) template="backend/shared.env" ;;
      */.env.*) template="${rel%.*}" ;;
      *) template="$rel" ;;
    esac
    src="$ROOT/$template.example"; dst="$ROOT/$rel"
    if [[ ! -f "$src" ]]; then echo "  -      $template.example (not found)"; return; fi
    if [[ -f "$dst" ]] && [[ "$force" == false ]]; then echo "  skip   $rel (exists; -f to overwrite)"; return; fi
    if [[ "$rel" == backend/shared.*.env && -f "$dst" ]]; then
      "$_PY" "$ROOT/scripts/env/init.py" "$dst" --refresh-from "$src" --environment "$runtime"
      _set_runtime "$dst"
      echo "  copied $rel (persistent encryption key kept)"
      return
    fi
    cp "$src" "$dst"
    _set_runtime "$dst"
    echo "  copied $rel"
  }

  case "$env" in
    dev)  for f in "${DEV_FILES[@]}"; do _copy_example "$f"; done ;;
    stg)  for f in "${STG_FILES[@]}"; do _copy_example "$f"; done ;;
    prod) for f in "${PROD_FILES[@]}"; do _copy_example "$f"; done ;;
  esac
  if [[ -f "$ROOT/backend/shared.$env.env" ]]; then
    "$_PY" "$ROOT/scripts/env/init.py" "$ROOT/backend/shared.$env.env" --ensure-key
  fi
  printf "\nDone. Fill in the remaining secrets before running the project.\n"
}

# ── migrate ──────────────────────────────────────────────────────────────────
cmd_migrate() {
  local env="${1:-}" old
  [[ $# -eq 1 ]] || { echo "usage: manage.sh migrate <dev|stg|prod>" >&2; exit 2; }
  case "$env" in
    dev|prod) old="" ;;
    stg) old=staging ;;
    *) echo "usage: manage.sh migrate <dev|stg|prod>" >&2; exit 2 ;;
  esac

  local sources=() targets=()
  if [[ -z "$old" ]]; then
    sources+=(".env" "backend/shared.env")
    targets+=(".env.$env" "backend/shared.$env.env")
    for service in api twitch discord scrapling; do
      sources+=("backend/$service/.env")
      targets+=("backend/$service/.env.$env")
    done
  else
    sources+=(".env.$old" "backend/shared.$old.env")
    targets+=(".env.$env" "backend/shared.$env.env")
    for service in api twitch discord scrapling; do
      sources+=("backend/$service/.env.$old")
      targets+=("backend/$service/.env.$env")
    done
    for kind in variables secrets; do
      sources+=(".github/$kind/$old.env")
      targets+=(".github/$kind/$env.env")
    done
  fi

  local i src dst
  for i in "${!sources[@]}"; do
    src="$ROOT/${sources[$i]}"; dst="$ROOT/${targets[$i]}"
    if [[ -f "$src" && -e "$dst" ]]; then
      echo "error: both ${sources[$i]} and ${targets[$i]} exist" >&2
      exit 1
    fi
  done

  local moved=0
  for i in "${!sources[@]}"; do
    src="$ROOT/${sources[$i]}"; dst="$ROOT/${targets[$i]}"
    [[ -f "$src" ]] || continue
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    echo "  ${sources[$i]} -> ${targets[$i]}"
    moved=$((moved + 1))
  done
  [[ $moved -gt 0 ]] || echo "No legacy $env env files found."
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
  _each_section _cp_env
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

  cmd_snapshot

  local date out
  date="$(date +%Y%m%d)"
  out="$DATA/env-$date.tar.gz"
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
      echo "  -     $rel (not in snapshot)"; skipped=$((skipped + 1)); return
    fi
    if [[ -f "$dst" ]] && [[ "$force" == false ]]; then
      echo "  skip  $rel (exists; -f to overwrite)"; skipped=$((skipped + 1)); return
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"; echo "  ✓  $rel"; copied=$((copied + 1))
  }

  printf "══ Restore  ←  %s\n\n" "$snap"
  _each_section _import_env
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

  _diff_file() {
    local rel="$1" cur="$ROOT/$1" old="$snap/$1"
    if   [[ ! -f "$cur" && ! -f "$old" ]]; then
      return
    elif [[ ! -f "$old" ]]; then
      echo "  + $rel  (new — not in snapshot)"; changed=$((changed + 1))
    elif [[ ! -f "$cur" ]]; then
      echo "  ✗ $rel  (missing locally)";       missing=$((missing + 1))
    elif ! diff -q "$cur" "$old" &>/dev/null; then
      echo "  ~ $rel"
      diff --unified=0 --label snapshot --label current "$old" "$cur" \
        | tail -n +3 | head -30 || true
      echo ""
      changed=$((changed + 1))
    else
      printf "    %s\n" "$rel"; same=$((same + 1))
    fi
  }

  _each_section _diff_file
  printf "\n%d changed  |  %d missing locally  |  %d unchanged\n" \
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
  migrate)  cmd_migrate  "$@" ;;
  snapshot) cmd_snapshot "$@" ;;
  backup)   cmd_backup   "$@" ;;
  restore)  cmd_restore  "$@" ;;
  diff)     cmd_diff     "$@" ;;
  list)     cmd_list ;;
  clean)    cmd_clean    "$@" ;;
  *)
    cat <<'EOF'
Usage: npm run nb -- env <command>   (or: bash scripts/env/manage.sh <command> [options])

  init      [dev|stg|prod] [-f]  Copy templates; defaults to dev
  migrate   <dev|stg|prod>       Rename legacy env files; target is required
  snapshot  [--keep N]        Snapshot live env files to data/env/YYYYMMDD/
  backup    [--keep N]        Snapshot + compress to data/env-YYYYMMDD.tar.gz
  restore   <DATE|FILE> [-f]  Restore from snapshot or .tar.gz  (-f overwrites)
  diff      [DATE|FILE]       Diff current env files against a snapshot
  list                        List available snapshots and backups
  clean     [--keep N]        Delete old snapshots/backups (default: keep 3)
EOF
    ;;
esac
