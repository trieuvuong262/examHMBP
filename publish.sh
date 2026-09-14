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
VPS_TAILSCALE_HOST="${VPS_TAILSCALE_HOST:-100.79.206.125}"
SSH_ID_ARGS=()
if [[ -n "${VPS_SSH_KEY:-}" && -f "${VPS_SSH_KEY}" ]]; then
  SSH_ID_ARGS=(-i "${VPS_SSH_KEY}" -o IdentitiesOnly=yes)
elif [[ -f "${HOME}/.ssh/vps_portal" ]]; then
  SSH_ID_ARGS=(-i "${HOME}/.ssh/vps_portal" -o IdentitiesOnly=yes)
fi

ssh_port_open() {
  local host_="$1"
  if command -v timeout >/dev/null 2>&1; then
    timeout 2 bash -c "echo >/dev/tcp/${host_}/${VPS_PORT}" 2>/dev/null
  else
    bash -c "echo >/dev/tcp/${host_}/${VPS_PORT}" 2>/dev/null
  fi
}

CANDIDATES=()
[[ -n "${VPS_TAILSCALE_HOST}" ]] && CANDIDATES+=("${VPS_TAILSCALE_HOST}")
[[ "${VPS_HOST}" != "${VPS_TAILSCALE_HOST}" ]] && CANDIDATES+=("${VPS_HOST}")

SSH_HOST=""
echo ""
echo "==> Chọn SSH host (Tailscale trước, IP public sau)"
for h in "${CANDIDATES[@]}"; do
  echo "    probe ${h}:${VPS_PORT} ..."
  if ssh_port_open "$h"; then
    SSH_HOST="$h"
    echo "    OK: $h"
    break
  fi
  echo "    timeout: $h"
done
[[ -z "${SSH_HOST}" ]] && SSH_HOST="${CANDIDATES[0]}"

echo "==> SSH deploy ${VPS_USER}@${SSH_HOST}:${VPS_PORT}"
ssh_deploy() {
  ssh -p "${VPS_PORT}" -o BatchMode=yes -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=accept-new \
    "${SSH_ID_ARGS[@]}" \
    "${VPS_USER}@$1" \
    "set -Eeuo pipefail; cd '${PROJECT_DIR}' && BRANCH='${BRANCH}' ./deploy.sh"
}

DEPLOY_OK=0
if ssh_deploy "${SSH_HOST}"; then
  DEPLOY_OK=1
else
  for h in "${CANDIDATES[@]}"; do
    [[ "$h" == "${SSH_HOST}" ]] && continue
    echo "==> Retry SSH ${VPS_USER}@${h}:${VPS_PORT}"
    if ssh_deploy "$h"; then
      DEPLOY_OK=1
      break
    fi
  done
fi

if [[ "${DEPLOY_OK}" != 1 ]]; then
  echo ""
  echo "SSH deploy failed. Test: ssh ${VPS_USER}@${SSH_HOST}"
  exit 1
fi

echo ""
echo "Xong: đã push và deploy trên VPS."
