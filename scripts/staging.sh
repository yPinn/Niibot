#!/usr/bin/env bash
# Staging environment management.
#
# Usage: bash scripts/staging.sh <command> [options]
#
#   up [profile]          Start staging  (profiles: api | twitch | discord | bots | full)
#   down                  Stop all, preserve volumes
#   reset                 Stop all and remove volumes (clean slate)
#   build [service]       Build or rebuild images
#   logs [service]        Follow logs (all if none specified)
#   ps                    Show container status
#   restart [service]     Restart all or specific service
#   migrate               Run database migrations
#   exec <service> [cmd]  Execute in container (default: bash)
#
# Profiles:
#   api     → api  (+ postgres always)
#   twitch  → twitch-bot
#   discord → discord-bot + instafix
#   bots    → twitch-bot + discord-bot + instafix
#   full    → all services  ← use for down/reset to stop everything
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Staging root env: injects POSTGRES_USER/PASSWORD/DB, etc.
# Written by CI/CD deploy workflow; must exist before running any command.
[[ -f "$ROOT/.env.staging" ]] || { echo "error: $ROOT/.env.staging not found"; exit 1; }

# Base compose command:
#   -p niibot-staging          isolates project name → separate containers, network, volumes from prod
#   --env-file .env.staging    injects root env (DB credentials, ports) into compose variable substitution
#   -f docker-compose.yml      base service definitions (images, healthchecks, shared config)
#   -f docker-compose.staging.yml  staging overrides (ports 8001/5434/3004, -stg container names)
DC=(docker compose
    -p niibot-staging
    --env-file "$ROOT/.env.staging"
    -f "$ROOT/docker-compose.yml"
    -f "$ROOT/docker-compose.staging.yml")

CMD="${1:-}"
shift 2>/dev/null || true

case "$CMD" in
  up)
    # Default profile "full" starts everything; pass a specific profile to start a subset.
    PROFILE="${1:-full}"
    echo "Starting staging (profile: $PROFILE)..."
    "${DC[@]}" --profile "$PROFILE" up -d
    ;;

  down)
    # --profile full required: plain `down` only stops profile-less services (postgres, migrate).
    # Services with profiles (api, discord-bot, twitch-bot, instafix) stay running
    # without it.
    echo "Stopping staging..."
    "${DC[@]}" --profile full down --remove-orphans
    ;;

  reset)
    # Same as down but also wipes volumes (postgres data, etc.).
    echo "Resetting staging (removing volumes)..."
    "${DC[@]}" --profile full down --remove-orphans -v
    ;;

  build)
    # Build one service or all if none specified. Passes remaining args as service names.
    "${DC[@]}" build ${1:+"$@"}
    ;;

  logs)
    # Stream logs. Pass a service name to tail a single container.
    "${DC[@]}" logs -f ${1:+"$@"}
    ;;

  ps)
    # Show running containers and their health status for this project only.
    "${DC[@]}" ps
    ;;

  restart)
    # Restart running containers (no rebuild). Operates by container name — no profile needed.
    "${DC[@]}" restart ${1:+"$@"}
    ;;

  migrate)
    # Run migrations as a one-shot container (same as CI/CD deploy workflow).
    # `run --rm` starts postgres via depends_on, runs migrations, then removes the container.
    echo "Running migrations..."
    "${DC[@]}" run --rm migrate
    ;;

  exec)
    # Open a shell (or run a command) inside a running container.
    [[ -z "${1:-}" ]] && { echo "error: exec requires a service name"; exit 1; }
    SERVICE="$1"; shift
    "${DC[@]}" exec "$SERVICE" "${@:-bash}"
    ;;

  *)
    sed -n '/^# Usage/,/^# Profiles/{ /^#/{ s/^# \?//; p } }' "$0"
    ;;
esac
