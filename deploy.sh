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

run_migrate_service() {
  local label="$1"
  echo "==> ${label}"
  compose run --rm --build migrate
}

run_manage() {
  compose run --rm --no-deps --build \
    -v "${PROJECT_DIR}:/app" \
    web python manage.py "$@"
}

cleanup_stale_files() {
  echo "==> Cleanup stale / redundant files"

  # File/thư mục không còn trong git sau khi pull (trừ dữ liệu runtime)
  if git clean -ffdn \
    -e .env \
    -e .env.local \
    -e media \
    -e media/ \
    -e staticfiles \
    -e staticfiles/ \
    -e '*.log' 2>/dev/null | grep -q .; then
    echo "    Removing untracked leftover paths:"
    git clean -ffdn \
      -e .env \
      -e .env.local \
      -e media \
      -e media/ \
      -e staticfiles \
      -e staticfiles/ \
      -e '*.log' 2>/dev/null | sed 's/^/      /'
    git clean -ffd \
      -e .env \
      -e .env.local \
      -e media \
      -e media/ \
      -e staticfiles \
      -e staticfiles/ \
      -e '*.log' 2>/dev/null || true
  else
    echo "    No untracked leftover paths."
  fi

  # Cache Python trên host (dev/deploy dir)
  local removed_cache=0
  while IFS= read -r -d '' dir; do
    rm -rf "${dir}"
    removed_cache=$((removed_cache + 1))
  done < <(find "${PROJECT_DIR}" -type d -name '__pycache__' -not -path '*/.git/*' -print0 2>/dev/null || true)
  while IFS= read -r -d '' file; do
    rm -f "${file}"
    removed_cache=$((removed_cache + 1))
  done < <(find "${PROJECT_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -not -path '*/.git/*' -print0 2>/dev/null || true)

  if [[ "${removed_cache}" -gt 0 ]]; then
    echo "    Removed ${removed_cache} Python cache path(s)."
  else
    echo "    No Python cache to remove."
  fi

  # File tracked cũ đã bị xóa trên repo nhưng còn sót local
  local deleted_in_repo
  deleted_in_repo="$(git ls-files --deleted 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${deleted_in_repo}" -gt 0 ]]; then
    echo "    Pruning ${deleted_in_repo} file(s) deleted in git:"
    git ls-files --deleted 2>/dev/null | sed 's/^/      /'
    git ls-files --deleted -z 2>/dev/null | xargs -0 -r rm -f
  fi
}

ensure_migrations() {
  echo "==> Ensure migrations are up to date (makemigrations check only)"
  if ! run_manage makemigrations --check --dry-run >/dev/null 2>&1; then
    echo "ERROR: Model changes chưa có migration trên repo."
    echo "       Chạy makemigrations ở máy dev, commit và push rồi deploy lại."
    echo "       Không tự tạo migration trên VPS — tránh lệch index/schema."
    run_manage makemigrations --check --dry-run || true
    exit 1
  else
    echo "    Migration files match models."
  fi
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

ensure_ssl_conf() {
  echo "==> Ensure nginx SSL config"
  local ssl_conf="${PROJECT_DIR}/PortalJustPlay/nginx/ssl.conf"
  local ssl_example="${PROJECT_DIR}/PortalJustPlay/nginx/ssl.conf.example"
  if ! grep -qE '^USE_HTTPS=(1|true|yes|on)' .env 2>/dev/null; then
    echo "    HTTPS disabled in .env — skip."
    return 0
  fi
  if [[ -d "${ssl_conf}" ]]; then
    echo "    WARNING: ${ssl_conf} is a directory (broken Docker bind) — removing."
    rm -rf "${ssl_conf}"
  fi
  if [[ ! -f "${ssl_conf}" ]]; then
    if [[ ! -f "${ssl_example}" ]]; then
      echo "ERROR: USE_HTTPS=1 but missing ${ssl_conf} and ${ssl_example}"
      exit 1
    fi
    cp "${ssl_example}" "${ssl_conf}"
    echo "    Created ${ssl_conf} from ssl.conf.example"
  else
    echo "    ${ssl_conf} OK"
  fi
}

ensure_agent_gate_env() {
  echo "==> Ensure agent gate .env keys"
  local env_file="${PROJECT_DIR}/.env"
  local secret_line=""
  if grep -q '^EQUIPMENT_AGENT_SECRET=' "${env_file}" 2>/dev/null; then
    secret_line="$(grep '^EQUIPMENT_AGENT_SECRET=' "${env_file}" | tail -1)"
  fi
  if ! grep -q '^EQUIPMENT_REQUIRE_AGENT_INSTALL=' "${env_file}" 2>/dev/null; then
    echo "EQUIPMENT_REQUIRE_AGENT_INSTALL=1" >> "${env_file}"
    echo "    Added EQUIPMENT_REQUIRE_AGENT_INSTALL=1"
  fi
  if ! grep -q '^EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES=' "${env_file}" 2>/dev/null; then
    echo "EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES=admin" >> "${env_file}"
    echo "    Added EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES=admin"
  fi
  if [[ -z "${secret_line}" ]]; then
    echo "    WARNING: EQUIPMENT_AGENT_SECRET chua co — gate hien nhung file cai khong hoat dong."
    echo "             Them EQUIPMENT_AGENT_SECRET=... vao .env roi deploy lai."
  fi
  if ! grep -q '^PORTAL_PUBLIC_BASE_URL=' "${env_file}" 2>/dev/null; then
    local base_url="http://${PORTAL_DOMAIN:-portal.justplay.vn}"
    if grep -qE '^USE_HTTPS=(1|true|yes|on)' "${env_file}" 2>/dev/null; then
      base_url="https://${PORTAL_DOMAIN:-portal.justplay.vn}"
    fi
    echo "PORTAL_PUBLIC_BASE_URL=${base_url}" >> "${env_file}"
    echo "    Added PORTAL_PUBLIC_BASE_URL=${base_url}"
  fi
}

ensure_agent_gate_env

echo "==> 1) Pull latest code"
git fetch --all --prune
git checkout "${BRANCH}"
# VPS là môi trường deploy — luôn khớp origin, không giữ sửa tay/hotfix local
if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git status --porcelain)" ]]; then
  echo "    Local changes detected — resetting to origin/${BRANCH}"
fi
git reset --hard "origin/${BRANCH}"
git clean -ffd \
  -e .env \
  -e .env.local \
  -e media \
  -e media/ \
  -e staticfiles \
  -e staticfiles/ \
  -e static/equipment/JustPlayAgent.exe \
  -e '*.log' 2>/dev/null || true
echo "    At commit: $(git rev-parse --short HEAD)"

echo "==> 2) Cleanup stale files from previous deploy"
cleanup_stale_files

echo "==> 3) Start database"
compose up -d db
wait_for_db

echo "==> 4) Create migrations if models changed"
ensure_migrations

echo "==> 5) Run migrations (before start web)"
run_migrate_service "migrate --noinput via migrate service"

ensure_ssl_conf

echo "==> 6) Build and start app services"
compose up -d --build web nginx

echo "==> 7) Run migrations again on running web"
compose exec -T web python manage.py migrate --noinput

verify_migrations

verify_agent_exe() {
  echo "==> Verify JustPlayAgent.exe"
  local exe_host="${PROJECT_DIR}/static/equipment/JustPlayAgent.exe"
  if [[ ! -f "${exe_host}" ]]; then
    echo "    WARNING: Thieu ${exe_host}"
    echo "             Tren may Windows: scripts/build-justplay-agent.cmd"
    echo "             Copy len VPS: static/equipment/JustPlayAgent.exe"
    return 0
  fi
  if compose exec -T web test -f /app/static/equipment/JustPlayAgent.exe; then
    echo "    JustPlayAgent.exe OK ($(wc -c < "${exe_host}" | tr -d ' ') bytes)"
  else
    echo "    WARNING: Container chua thay JustPlayAgent.exe — kiem tra volume mount."
  fi
}

verify_agent_gate() {
  echo "==> Verify agent install gate"
  if compose exec -T web python manage.py check_agent_gate 2>/dev/null; then
    return 0
  fi
  compose exec -T web python - <<'PY' || true
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
import django
django.setup()
from django.conf import settings
print("EQUIPMENT_REQUIRE_AGENT_INSTALL:", settings.EQUIPMENT_REQUIRE_AGENT_INSTALL)
print("EQUIPMENT_AGENT_SECRET_SET:", bool(settings.EQUIPMENT_AGENT_SECRET))
PY
}

verify_agent_gate
verify_agent_exe

verify_nas_rclone() {
  echo "==> Verify NAS rclone in web container"
  if compose exec -T web rclone lsd synology:DATACHUNG >/dev/null 2>&1; then
    echo "    NAS rclone OK (synology:DATACHUNG)"
  else
    echo "    WARNING: rclone không kết nối được NAS trong container."
    echo "             Kiểm tra: /root/.config/rclone/rclone.conf và scripts/setup-rclone-nas.sh"
  fi
}

echo "==> 8) Collect static files (clear old assets)"
compose exec -T web python manage.py collectstatic --noinput --clear

echo "==> 9) Cleanup orphan media (files not referenced in DB/HTML)"
if grep -qE '^CLEANUP_ORPHAN_MEDIA=(0|false|no|off)' .env 2>/dev/null; then
  echo "    Skipped (CLEANUP_ORPHAN_MEDIA is disabled in .env)."
else
  compose exec -T web python manage.py cleanup_orphan_media
fi

echo "==> 10) Show status"
compose ps

verify_nas_rclone

echo "==> 11) Cleanup old Docker images"
docker image prune -f

echo ""
echo "Deploy completed successfully."
echo ""
echo "Recurring tasks (công việc lặp): chạy cron hàng ngày:"
echo "  sudo bash scripts/setup-recurring-tasks-cron.sh"
echo ""
echo "Auto deploy: xem docs/HUONG_DAN_AUTO_DEPLOY.md"
echo "Optional — tạo dữ liệu demo:"
echo "  docker compose exec web python manage.py seed_demo_data"
