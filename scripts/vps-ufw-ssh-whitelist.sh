#!/usr/bin/env bash
# UFW: SSH (22) chỉ từ IP whitelist; HTTP/HTTPS vẫn mở toàn internet.
#
# Nguồn IP:
#   - scripts/vps-ssh-whitelist.conf (nếu có)
#   - Portal LoginSecurityConfig.wan_whitelist_ips (mặc định bật)
#   - Biến VPS_SSH_WHITELIST=ip1,ip2
#   - IP phiên SSH hiện tại ($SSH_CLIENT) — tránh tự khóa khi chạy qua SSH
#
# Chạy trên VPS:
#   bash scripts/vps-ufw-ssh-whitelist.sh
#   DRY_RUN=1 bash scripts/vps-ufw-ssh-whitelist.sh   # xem trước, không đổi UFW
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
cd "$PROJECT_DIR"

CONF_FILE="${CONF_FILE:-$PROJECT_DIR/scripts/vps-ssh-whitelist.conf}"
MERGE_PORTAL="${MERGE_PORTAL:-1}"
DRY_RUN="${DRY_RUN:-0}"

declare -A SEEN_IPS=()
COLLECTED=()

log() { echo "$@"; }

is_valid_ip() {
  python3 - "$1" <<'PY'
import ipaddress, sys
try:
    ipaddress.ip_address(sys.argv[1])
    sys.exit(0)
except ValueError:
    sys.exit(1)
PY
}

add_ip() {
  local raw="$1"
  local src="${2:-}"
  local ip
  ip="$(echo "$raw" | tr -d '[:space:]')"
  [[ -z "$ip" ]] && return 0
  if ! is_valid_ip "$ip"; then
    log "    Bỏ qua IP không hợp lệ ($src): $raw"
    return 0
  fi
  if [[ -n "${SEEN_IPS[$ip]:-}" ]]; then
    return 0
  fi
  SEEN_IPS[$ip]=1
  COLLECTED+=("$ip")
  log "    + $ip ($src)"
}

load_conf_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | tr -d '[:space:]')"
    [[ -z "$line" ]] && continue
    add_ip "$line" "conf"
  done <"$f"
}

load_portal_whitelist() {
  [[ "$MERGE_PORTAL" == "1" ]] || return 0
  if ! docker compose ps --status running web 2>/dev/null | grep -q web; then
    log "    Portal web chưa chạy — bỏ qua merge DB"
    return 0
  fi
  while IFS= read -r ip; do
    add_ip "$ip" "portal"
  done < <(docker compose exec -T web python - <<'PY' 2>/dev/null || true
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()
from audit.login_security import get_wan_whitelist

for item in get_wan_whitelist():
    print(item)
PY
)
}

load_env_whitelist() {
  [[ -n "${VPS_SSH_WHITELIST:-}" ]] || return 0
  local part
  IFS=',' read -ra parts <<<"${VPS_SSH_WHITELIST}"
  for part in "${parts[@]}"; do
    add_ip "$part" "env"
  done
}

load_ssh_client() {
  [[ -n "${SSH_CLIENT:-}" ]] || return 0
  local ip
  ip="$(echo "$SSH_CLIENT" | awk '{print $1}')"
  add_ip "$ip" "ssh-session"
}

collect_ips() {
  COLLECTED=()
  SEEN_IPS=()
  log "==> Thu thập IP whitelist SSH"
  load_conf_file "$CONF_FILE"
  if [[ ! -f "$CONF_FILE" ]]; then
    load_conf_file "$PROJECT_DIR/scripts/vps-ssh-whitelist.conf.example"
  fi
  load_portal_whitelist
  load_env_whitelist
  load_ssh_client
}

remove_ssh_allow_anywhere() {
  local max_pass=30 pass=0
  while (( pass < max_pass )); do
    local line num
    line="$(ufw status numbered 2>/dev/null | grep -E '22/tcp' | grep -E 'Anywhere|ALLOW IN' | head -1 || true)"
    [[ -z "$line" ]] && break
    num="$(echo "$line" | sed -nE 's/^\[[[:space:]]*([0-9]+)\].*/\1/p')"
    [[ -z "$num" ]] && break
    if [[ "$DRY_RUN" == "1" ]]; then
      log "    [dry-run] ufw delete $num  ($line)"
    else
      ufw --force delete "$num" >/dev/null
      log "    Đã xóa rule SSH mở toàn internet: #$num"
    fi
    pass=$((pass + 1))
  done
}

ensure_base_ufw() {
  if ! command -v ufw >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ufw
  fi
  if [[ -f /etc/ufw/ufw.conf ]] && grep -q '^DEFAULT_FORWARD_POLICY=' /etc/ufw/ufw.conf; then
    sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/ufw/ufw.conf
  fi
  if [[ "$DRY_RUN" != "1" ]]; then
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
  fi
}

apply_ssh_rules() {
  local ip
  for ip in "${COLLECTED[@]}"; do
    if ufw status 2>/dev/null | grep -Fq "ALLOW" && ufw status 2>/dev/null | grep -Fq "$ip" && ufw status 2>/dev/null | grep -Fq "22"; then
      log "    Giữ rule SSH cho $ip"
      continue
    fi
    if [[ "$DRY_RUN" == "1" ]]; then
      log "    [dry-run] ufw allow from $ip to any port 22 proto tcp"
    else
      ufw allow from "$ip" to any port 22 proto tcp comment "SSH whitelist" >/dev/null
      log "    Cho phép SSH từ $ip"
    fi
  done
}

ensure_web_ports() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "    [dry-run] ufw allow 80/tcp, 443/tcp"
    return 0
  fi
  ufw allow 80/tcp comment 'HTTP' >/dev/null 2>&1 || ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp comment 'HTTPS' >/dev/null 2>&1 || ufw allow 443/tcp >/dev/null
}

main() {
  collect_ips
  if [[ "${#COLLECTED[@]}" -eq 0 ]]; then
    echo "ERROR: Không có IP whitelist. Tạo $CONF_FILE hoặc cấu hình portal (tab Cấu hình IP)."
    echo "       Chạy qua SSH để tự thêm IP phiên hiện tại, hoặc đặt VPS_SSH_WHITELIST=ip1,ip2"
    exit 1
  fi

  log ""
  log "==> IP sẽ được phép SSH (${#COLLECTED[@]}): ${COLLECTED[*]}"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "==> DRY_RUN=1 — không thay đổi UFW"
  fi

  ensure_base_ufw
  remove_ssh_allow_anywhere
  apply_ssh_rules
  ensure_web_ports

  if [[ "$DRY_RUN" != "1" ]]; then
    if ! ufw status | grep -qi 'Status: active'; then
      ufw --force enable
    fi
    ufw reload >/dev/null 2>&1 || true
  fi

  log ""
  log "==> UFW status"
  ufw status verbose
  log ""
  log "Hoàn tất. SSH chỉ từ whitelist; 80/443 vẫn public."
  log "Cập nhật IP: sửa $CONF_FILE hoặc portal → chạy lại script này."
}

main
