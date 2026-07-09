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
  # Tránh cảnh báo Bake khi VPS chưa cài docker-buildx-plugin
  COMPOSE_BAKE="${COMPOSE_BAKE:-false}" docker compose "${compose_files[@]}" "$@"
}

# Image base — khớp Dockerfile (ARG PYTHON_BASE_IMAGE)
DOCKER_PYTHON_IMAGE="${DOCKER_PYTHON_IMAGE:-python:3.13-slim}"

pull_image_with_retry() {
  local image="$1"
  local max_attempts="${2:-5}"
  local attempt=1
  while [[ "${attempt}" -le "${max_attempts}" ]]; do
    echo "    pull ${image} (${attempt}/${max_attempts})..."
    if docker pull "${image}"; then
      echo "    OK: ${image}"
      return 0
    fi
    echo "    Failed (TLS timeout / Hub unreachable?) — retry in 15s..."
    sleep 15
    attempt=$((attempt + 1))
  done
  echo "ERROR: Cannot pull ${image} from Docker Hub."
  echo "    1) Thử lại: docker pull ${image}"
  echo "    2) Cấu hình mirror: scripts/docker-daemon-mirror.example.json → /etc/docker/daemon.json"
  echo "       rồi: systemctl restart docker"
  echo "    3) Hoặc build trên máy khác, docker save | scp | docker load"
  return 1
}

pull_deploy_images() {
  echo "    Pull Docker images (Hub / mirror)..."
  pull_image_with_retry "${DOCKER_PYTHON_IMAGE}" 5
  pull_image_with_retry "postgres:15-alpine" 3
  pull_image_with_retry "nginx:alpine" 3
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
  compose run --rm migrate
}

run_manage() {
  # Không --build ở đây: build một lần qua ensure_web_image() để tránh treo im lặng
  compose run --rm --no-deps \
    -v "${PROJECT_DIR}:/app" \
    web python manage.py "$@"
}

ensure_web_image() {
  echo "==> Build web Docker image (can take several minutes on first run)..."
  export DOCKER_PYTHON_IMAGE
  if ! compose build web; then
    echo "ERROR: docker compose build web failed."
    echo "    Thu: docker pull ${DOCKER_PYTHON_IMAGE}  (xem scripts/docker-daemon-mirror.example.json)"
    exit 1
  fi
  echo "    Web image ready."
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
  echo "    Running: python manage.py makemigrations --check --dry-run"
  if run_manage makemigrations --check --dry-run; then
    echo "    Migration files match models."
  else
    echo "ERROR: Model changes chưa có migration trên repo."
    echo "       Chạy makemigrations ở máy dev, commit và push rồi deploy lại."
    echo "       Không tự tạo migration trên VPS — tránh lệch index/schema."
    exit 1
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
  if ! compose exec -T web python manage.py showmigrations nas_storage 2>/dev/null | grep -q '0003_nasuserfolderaccess.*\[X\]'; then
    echo "    WARNING: Chua thay nas_storage.0003_nasuserfolderaccess — tinh nang Cap nhat link NAS chua san sang."
    echo "             Chay: docker compose exec web python manage.py migrate nas_storage"
  fi
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
  -e '*.log' 2>/dev/null || true
echo "    At commit: $(git rev-parse --short HEAD)"

echo "==> 2) Cleanup stale files from previous deploy"
cleanup_stale_files

echo "==> 3) Start database"
compose up -d db
wait_for_db

echo "==> 4) Pull base images + build web (tránh treo ở makemigrations)"
pull_deploy_images
ensure_web_image

echo "==> 5) Create migrations if models changed"
ensure_migrations

echo "==> 6) Run migrations (before start web)"
run_migrate_service "migrate --noinput via migrate service"

ensure_ssl_conf

echo "==> 7) Start app services"
export DOCKER_PYTHON_IMAGE
compose up -d web nginx

echo "==> 8) Run migrations again on running web"
compose exec -T web python manage.py migrate --noinput

verify_migrations

echo "==> 8b) Sync NPL category tree (nhóm cấp 1 + cấp 2)"
compose exec -T web python manage.py seed_kho_npl_category_tree

echo "==> 8c) Sync NPL colors + backfill material colors"
compose exec -T web python manage.py seed_kho_npl_material_colors

echo "==> 8d) Warm RaiDrive installer cache (tải nhanh từ đĩa VPS)"
compose exec -T web python manage.py warm_raidrive_installer_cache || echo "    WARNING: warm RaiDrive cache thất bại — kiểm tra NAS/share token"

verify_nas_rclone() {
  echo "==> Verify NAS rclone in web container"
  if compose exec -T web rclone lsd synology: >/dev/null 2>&1; then
    echo "    NAS rclone OK (synology: — user tailscale-justplay)"
  else
    echo "    WARNING: rclone không kết nối được NAS trong container."
    echo "             Kiểm tra: /root/.config/rclone/rclone.conf và scripts/setup-rclone-nas.sh"
  fi
  if compose exec -T web rclone lsd synology:backup >/dev/null 2>&1; then
    echo "    NAS backup folder OK (synology:backup)"
  else
    echo "    WARNING: Không thấy synology:backup — tạo shared folder 'backup' trên Synology"
    echo "             hoặc đặt NAS_BACKUP_RCLONE_REMOTE trong .env"
  fi
}

verify_nas_dsm() {
  echo "==> Verify NAS DSM API in web container"
  if compose exec -T web python manage.py shell -c "
from audit.services.nas_monitor import dsm_configured, collect_nas_metrics
if not dsm_configured():
    raise SystemExit('not configured')
m = collect_nas_metrics()
if m.get('error'):
    raise SystemExit(m['error'])
if m.get('cpu', {}).get('percent') is None and not m.get('processes'):
    raise SystemExit('no cpu/process data')
" >/dev/null 2>&1; then
    echo "    NAS DSM API OK (tailscale-justplay)"
  else
    echo "    WARNING: DSM API chưa kết nối được (CPU/RAM/tiến trình)."
    echo "             rclone SMB có thể OK trong khi cổng HTTPS DSM bị chặn."
    echo "             Synology: Login Portal → Web Services (cổng HTTPS), Firewall → mở cổng cho Tailscale."
    echo "             Test: docker compose exec web curl -k \"\${NAS_DSM_URL:-https://100.93.5.42:5556}/webapi/entry.cgi?api=SYNO.API.Info&version=1&method=query\""
  fi
}

echo "==> 9) PWA icons from static/images/logo/logo.png"
if [ -f "static/images/logo/logo.png" ]; then
  set +e
  compose exec -T web python scripts/generate_pwa_icons.py >/dev/null 2>&1
  pwa_rc=$?
  if [[ "${pwa_rc}" -ne 0 ]] && command -v python3 >/dev/null 2>&1; then
    python3 scripts/generate_pwa_icons.py >/dev/null 2>&1
    pwa_rc=$?
  fi
  set -e
  if [[ "${pwa_rc}" -eq 0 ]]; then
    echo "    PWA icons OK."
  else
    echo "    WARNING: skip PWA icons (optional — PIL not available)."
  fi
else
  echo "    WARNING: static/images/logo/logo.png missing — skip icon generation"
fi

echo "==> 10) Collect static files (clear old assets)"
compose exec -T web python manage.py collectstatic --noinput --clear

echo "==> 11) Cleanup orphan media (files not referenced in DB/HTML)"
if grep -qE '^CLEANUP_ORPHAN_MEDIA=(0|false|no|off)' .env 2>/dev/null; then
  echo "    Skipped (CLEANUP_ORPHAN_MEDIA is disabled in .env)."
else
  compose exec -T web python manage.py cleanup_orphan_media
fi

echo "==> 12) Show status"
compose ps

echo "==> 12a) Cron web push nhắc lịch (mỗi phút)"
if [[ -f scripts/setup-schedule-reminder-cron.sh ]]; then
  bash scripts/setup-schedule-reminder-cron.sh || echo "    WARNING: setup-schedule-reminder-cron.sh failed"
else
  echo "    WARNING: scripts/setup-schedule-reminder-cron.sh not found"
fi

verify_nas_rclone
verify_nas_dsm

echo "==> 13) Cleanup Docker build cache and unused images"
docker builder prune -af --filter "until=72h" 2>/dev/null || docker builder prune -af 2>/dev/null || true
docker image prune -f

echo ""
echo "Deploy completed successfully."
echo ""
echo "Recurring tasks (công việc lặp): chạy cron hàng ngày:"
echo "  sudo bash scripts/setup-recurring-tasks-cron.sh"
echo "Web push nhắc đặt cơm (16h–17h):"
echo "  python manage.py generate_webpush_vapid_keys   # lần đầu — copy vào .env"
echo "  sudo bash scripts/setup-meal-push-cron.sh"
echo "Web push nhắc lịch (mỗi phút):"
echo "  sudo bash scripts/setup-schedule-reminder-cron.sh"
echo "Backup NAS 00:00 hàng ngày (DB + source + media):"
echo "  sudo bash scripts/setup-backup-cron.sh"
echo ""
echo "Auto deploy: xem docs/HUONG_DAN_AUTO_DEPLOY.md"
echo "Optional — tạo dữ liệu demo:"
echo "  docker compose exec web python manage.py seed_demo_data"
