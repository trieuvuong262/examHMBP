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

# Deploy thẳng IP public — không probe / fallback Tailscale.
VPS_HOST="${VPS_HOST:-103.90.224.203}"
VPS_USER="${VPS_USER:-root}"
VPS_PORT="${VPS_PORT:-22}"
PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
BRANCH="${BRANCH:-main}"
VPS_SSH_KEY="${VPS_SSH_KEY:-${HOME}/.ssh/vps_portal}"
SSH_ID_ARGS=(-i "${VPS_SSH_KEY}" -o IdentitiesOnly=yes)

echo ""
echo "==> SSH deploy ${VPS_USER}@${VPS_HOST}:${VPS_PORT}"
echo "    ssh -i ${VPS_SSH_KEY} -p ${VPS_PORT} ${VPS_USER}@${VPS_HOST}"
if [[ ! -f "${VPS_SSH_KEY}" ]]; then
  echo "SSH key not found: ${VPS_SSH_KEY}"
  echo "Test: ssh -i ${HOME}/.ssh/vps_portal -p ${VPS_PORT} ${VPS_USER}@${VPS_HOST}"
  exit 1
fi

SSH_RC=0
ssh -p "${VPS_PORT}" -o BatchMode=yes -o ConnectTimeout=8 \
  -o StrictHostKeyChecking=accept-new \
  "${SSH_ID_ARGS[@]}" \
  "${VPS_USER}@${VPS_HOST}" \
  "set -Eeuo pipefail; cd '${PROJECT_DIR}' && BRANCH='${BRANCH}' ./deploy.sh" || SSH_RC=$?

if [[ "${SSH_RC}" -ne 0 ]]; then
  echo ""
  echo "SSH deploy failed. Test: ssh -i ${HOME}/.ssh/vps_portal -p ${VPS_PORT} ${VPS_USER}@${VPS_HOST}"
  exit "${SSH_RC}"
fi

echo ""
echo "Xong: đã push và deploy trên VPS."
