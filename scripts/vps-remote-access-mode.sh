#!/usr/bin/env bash
# Swap đường NAS Portal: Fortinet IPsec (LAN) <-> Tailscale.
# KHÔNG tắt tailscaled — mesh SSH 100.x giữ làm dự phòng.
#
#   bash scripts/vps-remote-access-mode.sh status
#   bash scripts/vps-remote-access-mode.sh fortinet
#   bash scripts/vps-remote-access-mode.sh tailscale
set -euo pipefail

MODE="${1:-status}"
FORTIGATE_WAN="${FORTIGATE_WAN_IP:-14.161.25.119}"
NAS_LAN="${NAS_LAN_HOST:-192.168.40.252}"
NAS_TS="${NAS_TS_HOST:-100.90.91.74}"
HOST_DIR="${HOST_PROJECT_DIR:-/opt/portaljustplay}"
ENV_FILE="${HOST_DIR}/.env"
RCLONE_CONF="${RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"
STATE_DIR="/etc/portaljustplay"
STATE_FILE="${STATE_DIR}/remote-access.mode"
TS_CIDR="100.64.0.0/10"

log() { echo "$@"; }

tcp_open() {
  timeout 5 bash -c "echo >/dev/tcp/${1}/${2}" 2>/dev/null
}

write_state() {
  mkdir -p "$STATE_DIR"
  echo "$1" > "$STATE_FILE"
  chmod 644 "$STATE_FILE"
}

ensure_ufw() {
  if ! command -v ufw >/dev/null 2>&1; then
    return 0
  fi
  ufw allow 80/tcp comment 'HTTP' >/dev/null 2>&1 || true
  ufw allow 443/tcp comment 'HTTPS' >/dev/null 2>&1 || true
}

ensure_rule() {
  local spec="$1"
  local comment="$2"
  command -v ufw >/dev/null 2>&1 || return 0
  if ufw status 2>/dev/null | grep -Fq "$spec"; then
    log "    giữ: $spec"
    return 0
  fi
  ufw allow $spec comment "$comment" >/dev/null
  log "    + ufw allow $spec"
}

rewrite_nas_hosts() {
  local new_host="$1"
  [[ -f "$ENV_FILE" ]] || { echo "ERROR: không thấy ${ENV_FILE}"; exit 1; }
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.remote-access"
  python3 - "$ENV_FILE" "$new_host" <<'PY'
import re, sys
path, host = sys.argv[1], sys.argv[2]
text = open(path, encoding='utf-8').read()

def sub_url(m):
    return f'{m.group(1)}{host}{m.group(2)}'

text, n_url = re.subn(
    r'^(NAS_DSM_URL=https?://)[^/:\s]+(.*)$', sub_url, text, flags=re.M,
)
for key in ('NAS_LDAP_HOST', 'NAS_SSH_HOST', 'NAS_SMB_HOST'):
    text, n = re.subn(rf'^{key}=.*$', f'{key}={host}', text, flags=re.M)
    if n == 0 and key != 'NAS_SMB_HOST':
        text = text.rstrip() + f'\n{key}={host}\n'
if n_url == 0:
    if re.search(r'^NAS_DSM_URL=', text, re.M):
        raise SystemExit('ERROR: NAS_DSM_URL có trong .env nhưng không parse được.')
    text = text.rstrip() + f'\nNAS_DSM_URL=https://{host}:5556\n'
open(path, 'w', encoding='utf-8').write(text)
print(f'    .env NAS host -> {host}')
PY
  if [[ -f "$RCLONE_CONF" ]]; then
    cp -a "$RCLONE_CONF" "${RCLONE_CONF}.bak.remote-access"
    python3 - "$RCLONE_CONF" "$NAS_TS" "$NAS_LAN" "$new_host" <<'PY'
import sys
path, ts, lan, new = sys.argv[1:5]
old = lan if new == ts else ts
text = open(path, encoding='utf-8').read()
text2 = text.replace(f'host = {old}', f'host = {new}')
if text2 != text:
    open(path, 'w', encoding='utf-8').write(text2)
    print(f'    rclone host {old} -> {new}')
else:
    print(f'    rclone: không có host = {old} (bỏ qua)')
PY
  else
    log "    rclone.conf không có — bỏ qua"
  fi
}

recreate_app() {
  if [[ ! -f "${HOST_DIR}/docker-compose.yml" ]]; then
    log "    WARN: không thấy docker-compose.yml — restart tay web/worker"
    return 0
  fi
  log "    recreate web + worker để nạp .env mới"
  docker compose -f "${HOST_DIR}/docker-compose.yml" --project-directory "${HOST_DIR}" \
    up -d --force-recreate --no-deps web worker
}

cmd_status() {
  local file_mode="unknown"
  [[ -f "$STATE_FILE" ]] && file_mode="$(tr -d '[:space:]' < "$STATE_FILE")"
  local ts="off"
  if systemctl is-active --quiet tailscaled 2>/dev/null; then
    ts="on"
  fi
  local dsm=""
  if [[ -f "$ENV_FILE" ]]; then
    dsm="$(grep -E '^NAS_DSM_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  fi
  echo "mode_file=${file_mode}"
  echo "tailscale=${ts}"
  echo "nas_dsm_url=${dsm}"
  echo "nas_lan=${NAS_LAN}"
  echo "nas_ts=${NAS_TS}"
  echo "fortigate_wan=${FORTIGATE_WAN}"
  echo "lan_445=$(tcp_open "$NAS_LAN" 445 && echo open || echo closed)"
  echo "lan_5556=$(tcp_open "$NAS_LAN" 5556 && echo open || echo closed)"
  echo "ts_5556=$(tcp_open "$NAS_TS" 5556 && echo open || echo closed)"
}

cmd_fortinet() {
  log "==> Swap NAS sang Fortinet IPsec (${NAS_LAN}) — Tailscale giữ chạy"
  if ! tcp_open "$NAS_LAN" 445 && ! tcp_open "$NAS_LAN" 5556; then
    echo "ERROR: NAS LAN ${NAS_LAN} chưa thông (445/5556). Không swap. Tailscale không đổi."
    exit 1
  fi
  ensure_ufw
  ensure_rule "from ${FORTIGATE_WAN} to any port 22 proto tcp" "SSH Fortinet WAN"
  ensure_rule "from ${FORTIGATE_WAN} to any port 500 proto udp" "IPsec IKE"
  ensure_rule "from ${FORTIGATE_WAN} to any port 4500 proto udp" "IPsec NAT-T"
  ensure_rule "from ${TS_CIDR} to any port 22 proto tcp" "SSH Tailscale"
  rewrite_nas_hosts "$NAS_LAN"
  recreate_app
  write_state fortinet
  log "    NAS đi ${NAS_LAN}. tailscaled không tắt."
}

cmd_tailscale() {
  log "==> Swap NAS về Tailscale (${NAS_TS}) — Tailscale giữ chạy"
  if ! systemctl is-active --quiet tailscaled 2>/dev/null; then
    systemctl enable --now tailscaled
    command -v tailscale >/dev/null 2>&1 && tailscale up --timeout=25s || true
  fi
  if ! tcp_open "$NAS_TS" 445 && ! tcp_open "$NAS_TS" 5556; then
    echo "ERROR: NAS Tailscale ${NAS_TS} chưa thông. Không swap."
    exit 1
  fi
  ensure_ufw
  ensure_rule "from ${FORTIGATE_WAN} to any port 22 proto tcp" "SSH Fortinet WAN"
  ensure_rule "from ${TS_CIDR} to any port 22 proto tcp" "SSH Tailscale"
  rewrite_nas_hosts "$NAS_TS"
  recreate_app
  write_state tailscale
  log "    NAS đi ${NAS_TS}. tailscaled vẫn chạy."
}

case "$MODE" in
  status) cmd_status ;;
  fortinet) cmd_fortinet ;;
  tailscale) cmd_tailscale ;;
  *)
    echo "Usage: $0 status|fortinet|tailscale"
    exit 2
    ;;
esac
