#!/usr/bin/env bash
# PortalJustPlay — git add, commit, push, (tuỳ chọn) SSH deploy.sh trên VPS
# Usage:
#   chmod +x publish.sh
#   ./publish.sh
#   ./publish.sh "sua menu nhan su"

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

COMMIT_MSG="${1:-update}"
ENV_FILE="${ROOT}/deploy.local.env"

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${ENV_FILE}" | sed 's/\r$//')
  set +a
}

echo "==> PortalJustPlay publish"
echo "    ${ROOT}"

if [[ ! -d .git ]]; then
  echo "ERROR: Không thấy .git — chạy trong thư mục PortalJustPlay."
  exit 1
fi

echo "==> git add ."
git add .

if [[ -n "$(git status --porcelain)" ]]; then
  echo "==> git commit -m \"${COMMIT_MSG}\""
  git commit -m "${COMMIT_MSG}"
else
  echo "    Không có thay đổi — bỏ qua commit."
fi

echo "==> git push"
git push

load_env

if [[ "${DEPLOY_AFTER_PUSH:-1}" == "0" || "${DEPLOY_AFTER_PUSH}" == "false" ]]; then
  echo ""
  echo "Đã push. DEPLOY_AFTER_PUSH=0 — không SSH deploy."
  exit 0
fi

if [[ -z "${VPS_HOST:-}" ]]; then
  echo ""
  echo "Đã push lên Git."
  echo "Deploy VPS: GitHub Actions (push main) hoặc tạo deploy.local.env — xem docs/HUONG_DAN_AUTO_DEPLOY.md"
  exit 0
fi

VPS_USER="${VPS_USER:-root}"
VPS_PORT="${VPS_PORT:-22}"
PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
BRANCH="${BRANCH:-main}"

echo ""
echo "==> SSH deploy ${VPS_USER}@${VPS_HOST}:${VPS_PORT}"
ssh -p "${VPS_PORT}" -o BatchMode=yes -o ConnectTimeout=15 \
  "${VPS_USER}@${VPS_HOST}" \
  "set -Eeuo pipefail; cd '${PROJECT_DIR}' && BRANCH='${BRANCH}' ./deploy.sh"

echo ""
echo "Xong: đã push và deploy trên VPS."
