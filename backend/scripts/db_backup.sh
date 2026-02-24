#!/usr/bin/env bash
# db_backup.sh — PostgreSQL backup via docker exec
#
# Usage (run from project root where docker-compose.yml lives):
#   bash backend/scripts/db_backup.sh
#
# Cron example (daily at 03:00, keep 7 days):
#   0 3 * * * cd /opt/niibot && bash backend/scripts/db_backup.sh >> data/backups/backup.log 2>&1
#
# Restoring a backup:
#   gunzip -c data/backups/niibot-20260224.sql.gz | \
#     docker exec -i niibot-postgres psql -U $POSTGRES_USER $POSTGRES_DB

set -euo pipefail

BACKUP_DIR="$(cd "$(dirname "$0")/../.." && pwd)/data/backups"
mkdir -p "$BACKUP_DIR"

# Load credentials from root .env (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER not set}"
: "${POSTGRES_DB:?POSTGRES_DB not set}"

FILENAME="niibot-$(date +%Y%m%d-%H%M).sql.gz"
OUTFILE="$BACKUP_DIR/$FILENAME"

echo "[$(date)] Starting backup → $OUTFILE"

docker exec niibot-postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$OUTFILE"

echo "[$(date)] Backup complete: $(du -h "$OUTFILE" | cut -f1)"

# Keep only last 7 backups
find "$BACKUP_DIR" -name "niibot-*.sql.gz" -type f \
  | sort -r | tail -n +8 | xargs -r rm --
