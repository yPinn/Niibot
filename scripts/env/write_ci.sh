#!/usr/bin/env bash
# Write deploy env files from GitHub values and env.manifest.json.
set -euo pipefail
umask 077

: "${SECRETS_JSON:?SECRETS_JSON is required (pass env: SECRETS_JSON: \${{ toJSON(secrets) }})}"
: "${VARS_JSON:?VARS_JSON is required (pass env: VARS_JSON: \${{ toJSON(vars) }})}"
: "${PROJECT_DIR:?PROJECT_DIR is required}"
: "${DEPLOY_ENVIRONMENT:?DEPLOY_ENVIRONMENT is required (production|staging)}"

export SECRETS_JSON VARS_JSON PROJECT_DIR DEPLOY_ENVIRONMENT
export DRY_RUN="${DRY_RUN:-}"

python3 "$PROJECT_DIR/scripts/env/ci.py"
