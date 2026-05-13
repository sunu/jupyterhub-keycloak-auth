#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: $ENV_FILE not found. Copy .env.example and fill in values." >&2
  exit 1
fi

set -a; source "$ENV_FILE"; set +a

export KEYCLOAK_CLIENT_SECRET="${STAGING_CLIENT_SECRET:?STAGING_CLIENT_SECRET must be set in .env}"
export JUPYTERHUB_CRYPT_KEY="${JUPYTERHUB_CRYPT_KEY:?JUPYTERHUB_CRYPT_KEY must be set in .env}"

echo "==> Starting Keycloak (Docker Compose)..."
docker compose -f "$ROOT/docker-compose.yml" up -d --wait

echo "==> Launching JupyterHub..."
exec jupyterhub -f "$ROOT/jupyterhub_config.py"
