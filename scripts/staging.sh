#!/usr/bin/env bash
# Staging environment management.
#
# Usage: bash scripts/staging.sh <command> [options]
#
#   up [profile]          Start staging  (profiles: api | twitch | discord | bots | full)
#   down                  Stop, preserve volumes
#   reset                 Stop and remove volumes (clean slate)
#   build [service]       Build or rebuild images
#   logs [service]        Follow logs (all if none specified)
#   ps                    Show container status
#   restart [service]     Restart all or specific service
#   migrate               Run database migrations
#   exec <service> [cmd]  Execute in container (default: bash)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

[[ -f "$ROOT/.env.staging" ]] || { echo "error: $ROOT/.env.staging not found"; exit 1; }

DC=(docker compose -p niibot-staging --env-file "$ROOT/.env.staging"
    -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.staging.yml")

CMD="${1:-}"
shift 2>/dev/null || true

case "$CMD" in
  up)
    PROFILE="${1:-full}"
    echo "Starting staging (profile: $PROFILE)..."
    "${DC[@]}" --profile "$PROFILE" up -d
    ;;

  down)
    echo "Stopping staging..."
    "${DC[@]}" down --remove-orphans
    ;;

  reset)
    echo "Resetting staging (removing volumes)..."
    "${DC[@]}" down --remove-orphans -v
    ;;

  build)
    "${DC[@]}" build ${1:+"$@"}
    ;;

  logs)
    "${DC[@]}" logs -f ${1:+"$@"}
    ;;

  ps)
    "${DC[@]}" ps
    ;;

  restart)
    "${DC[@]}" restart ${1:+"$@"}
    ;;

  migrate)
    echo "Running migrations..."
    "${DC[@]}" up migrate
    ;;

  exec)
    [[ -z "${1:-}" ]] && { echo "error: exec requires a service name"; exit 1; }
    SERVICE="$1"; shift
    "${DC[@]}" exec "$SERVICE" "${@:-bash}"
    ;;

  *)
    sed -n '/^# Usage/,/^set /{ /^#/{ s/^# \?//; p }; /^set /q }' "$0"
    ;;
esac
