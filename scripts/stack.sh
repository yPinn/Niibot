#!/usr/bin/env bash
# Explicit Compose entry point: one env, project, and overlay per invocation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-}"
CMD="${2:-}"
[[ -n "$TARGET" ]] && shift || true
[[ -n "$CMD" ]] && shift || true

case "$TARGET" in
  dev|stg|prod) ;;
  *) echo "usage: stack.sh <dev|stg|prod> <command> [args]" >&2; exit 2 ;;
esac

ENV_FILE="$ROOT/.env.$TARGET"
[[ -f "$ENV_FILE" ]] || { echo "error: $ENV_FILE not found" >&2; exit 1; }

PROJECT="niibot-$TARGET"
DC=(docker compose
    -p "$PROJECT"
    --env-file "$ENV_FILE"
    -f "$ROOT/compose.yaml"
    -f "$ROOT/compose.$TARGET.yaml")

case "$CMD" in
  up)
    PROFILE="${1:-full}"
    "${DC[@]}" --profile "$PROFILE" up -d --remove-orphans
    ;;
  down)
    "${DC[@]}" --profile full down --remove-orphans
    ;;
  reset)
    [[ "$TARGET" != "prod" ]] || { echo "error: prod reset is disabled" >&2; exit 2; }
    "${DC[@]}" --profile full down --remove-orphans -v
    if [[ "$TARGET" == "stg" ]]; then
      # Compose -v cannot remove the staging PostgreSQL bind mount.
      rm -rf -- "$ROOT/data/staging/postgres"
    fi
    ;;
  build)
    "${DC[@]}" build "$@"
    ;;
  logs)
    "${DC[@]}" logs -f "$@"
    ;;
  ps)
    "${DC[@]}" ps
    ;;
  restart)
    "${DC[@]}" restart "$@"
    ;;
  migrate)
    "${DC[@]}" run --rm migrate
    ;;
  exec)
    [[ -n "${1:-}" ]] || { echo "error: exec requires a service" >&2; exit 2; }
    SERVICE="$1"; shift
    if [[ $# -gt 0 ]]; then
      "${DC[@]}" exec "$SERVICE" "$@"
    else
      "${DC[@]}" exec "$SERVICE" bash
    fi
    ;;
  config)
    "${DC[@]}" config --quiet
    ;;
  *)
    echo "usage: stack.sh <dev|stg|prod> <up|down|reset|build|logs|ps|restart|migrate|exec|config> [args]" >&2
    exit 2
    ;;
esac
