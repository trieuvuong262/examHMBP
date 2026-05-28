#!/usr/bin/env bash
set -Eeuo pipefail

# ===============================
# PortalJustPlay deploy script
# ===============================
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Optional env:
#   PROJECT_DIR=/opt/portaljustplay BRANCH=main ./deploy.sh

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo "==> Deploying PortalJustPlay"
echo "    PROJECT_DIR: ${PROJECT_DIR}"
echo "    BRANCH:      ${BRANCH}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "ERROR: Project directory not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "ERROR: ${COMPOSE_FILE} not found in ${PROJECT_DIR}"
  echo "Hint: run 'ls -la' and check compose filename."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found in ${PROJECT_DIR}"
  exit 1
fi

echo "==> 1) Pull latest code"
git fetch --all --prune
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "==> 2) Start database first"
docker compose -f "${COMPOSE_FILE}" up -d db

echo "==> 3) Run migrations + collectstatic"
docker compose -f "${COMPOSE_FILE}" run --rm migrate

echo "==> 4) Build and start app services"
docker compose -f "${COMPOSE_FILE}" up -d --build web nginx

if docker compose -f "${COMPOSE_FILE}" config --services | grep -qx "metabase"; then
  echo "==> 5) Start metabase"
  docker compose -f "${COMPOSE_FILE}" up -d metabase
fi

echo "==> 6) Run collectstatic on running web"
docker compose -f "${COMPOSE_FILE}" exec -T web python manage.py collectstatic --noinput

echo "==> 7) Show status"
docker compose -f "${COMPOSE_FILE}" ps

echo "==> 8) Cleanup old images"
docker image prune -f

echo "Deploy completed successfully."
