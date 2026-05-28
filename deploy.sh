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

compose_files=(-f "${COMPOSE_FILE}")
if [[ -f "docker-compose.ssl.yml" ]] && grep -qE '^USE_HTTPS=(1|true|yes|on)' .env 2>/dev/null; then
  compose_files+=(-f docker-compose.ssl.yml)
fi

compose() {
  docker compose "${compose_files[@]}" "$@"
}

wait_for_db() {
  echo "==> Waiting for database..."
  local attempt=1
  local max_attempts=30
  while [[ "${attempt}" -le "${max_attempts}" ]]; do
    if compose ps db 2>/dev/null | grep -q "(healthy)"; then
      echo "    Database is healthy."
      return 0
    fi
    echo "    attempt ${attempt}/${max_attempts}..."
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "ERROR: Database not healthy after ${max_attempts} attempts."
  compose ps db || true
  exit 1
}

run_migrations() {
  local label="$1"
  echo "==> ${label}"
  compose run --rm --build migrate
}

verify_migrations() {
  echo "==> Verify migrations (no pending)"
  local pending
  pending="$(compose exec -T web python manage.py showmigrations --plan | grep -c '\[ \]' || true)"
  if [[ "${pending}" -gt 0 ]]; then
    echo "ERROR: ${pending} migration(s) still pending."
    compose exec -T web python manage.py showmigrations
    exit 1
  fi
  echo "    All migrations applied."
}

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

echo "==> 2) Start database"
compose up -d db
wait_for_db

echo "==> 3) Run migrations (before start web)"
run_migrations "migrate --noinput via migrate service"

echo "==> 4) Build and start app services"
compose up -d --build web nginx

echo "==> 5) Run migrations again on running web"
compose exec -T web python manage.py migrate --noinput

verify_migrations

echo "==> 6) Collect static files"
compose exec -T web python manage.py collectstatic --noinput

echo "==> 7) Show status"
compose ps

echo "==> 8) Cleanup old images"
docker image prune -f

echo ""
echo "Deploy completed successfully."
echo ""
echo "Auto deploy: xem docs/HUONG_DAN_AUTO_DEPLOY.md"
echo "Optional — tạo dữ liệu demo:"
echo "  docker compose exec web python manage.py seed_demo_data"
