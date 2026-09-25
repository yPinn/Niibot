#!/usr/bin/env bash
# Stream a PostgreSQL dump through the selected Compose project.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TARGET="${1:-dev}"
case "$TARGET" in
  dev|stg|prod) ;;
  *) echo "usage: db_backup.sh [dev|stg|prod]" >&2; exit 2 ;;
esac

ENV_FILE="$ROOT/.env.$TARGET"
[[ -f "$ENV_FILE" ]] || { echo "error: $ENV_FILE not found" >&2; exit 1; }

BACKUP_DIR="$ROOT/data/backups/$TARGET"
mkdir -p "$BACKUP_DIR"
OUTFILE="$BACKUP_DIR/niibot-$(date +%Y%m%d-%H%M).sql.gz"
DC=(docker compose
    -p "niibot-$TARGET"
    --env-file "$ENV_FILE"
    -f "$ROOT/compose.yaml"
    -f "$ROOT/compose.$TARGET.yaml")

echo "[$(date)] Backing up $TARGET to $OUTFILE"
"${DC[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$OUTFILE"
echo "[$(date)] Backup complete: $(du -h "$OUTFILE" | cut -f1)"

find "$BACKUP_DIR" -name 'niibot-*.sql.gz' -type f \
  | sort -r | tail -n +8 \
  | while IFS= read -r file; do rm -- "$file"; done
