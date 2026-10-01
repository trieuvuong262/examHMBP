#!/usr/bin/env bash
# Đường NAS Portal qua VPN site-to-site (IPsec Fortigate VPS <-> văn phòng).
# DSM / rclone / LDAP / SSH backup trỏ IP LAN của NAS. Không dùng Tailscale.
#
#   bash scripts/vps-nas-site-to-site.sh status
#   bash scripts/vps-nas-site-to-site.sh apply
#   DISABLE_TAILSCALE=1 bash scripts/vps-nas-site-to-site.sh apply   # tắt hẳn tailscaled
set -euo pipefail

MODE="${1:-status}"
FORTIGATE_WAN="${FORTIGATE_WAN_IP:-14.161.25.119}"
NAS_LAN="${NAS_LAN_HOST:-192.168.40.252}"
DISABLE_TS="${DISABLE_TAILSCALE:-0}"
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

delete_rule() {
  local spec="$1"
  command -v ufw >/dev/null 2>&1 || return 0
  if ufw status 2>/dev/null | grep -Fq "$spec"; then
    ufw delete allow $spec >/dev/null || true
    log "    - ufw delete allow $spec"
  fi
}

rewrite_nas_hosts() {
  [[ -f "$ENV_FILE" ]] || { echo "ERROR: không thấy ${ENV_FILE}"; exit 1; }
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.site-to-site"
  python3 - "$ENV_FILE" "$NAS_LAN" <<'PY'
import re, sys
path, host = sys.argv[1], sys.argv[2]
text = open(path, encoding='utf-8').read()

def sub_url(m):
    return f'{m.group(1)}{host}{m.group(2)}'

text, n_url = re.subn(
    r'^(NAS_DSM_URL=https?://)[^/:\s]+(.*)$', sub_url, text, flags=re.M,
)
for key in ('NAS_LAN_HOST', 'NAS_LDAP_HOST', 'NAS_SSH_HOST', 'NAS_SMB_HOST', 'NAS_BACKUP_SSH_HOST'):
    text, n = re.subn(rf'^{key}=.*$', f'{key}={host}', text, flags=re.M)
    if n == 0 and key != 'NAS_SMB_HOST':
        text = text.rstrip() + f'\n{key}={host}\n'
text = re.sub(r'^NAS_TS_HOST=.*\n?', '', text, flags=re.M)
if n_url == 0:
    if re.search(r'^NAS_DSM_URL=', text, re.M):
        raise SystemExit('ERROR: NAS_DSM_URL có trong .env nhưng không parse được.')
    text = text.rstrip() + f'\nNAS_DSM_URL=https://{host}:5556\n'
open(path, 'w', encoding='utf-8').write(text)
print(f'    .env NAS host -> {host}')
PY
  if [[ -f "$RCLONE_CONF" ]]; then
    cp -a "$RCLONE_CONF" "${RCLONE_CONF}.bak.site-to-site"
    python3 - "$RCLONE_CONF" "$NAS_LAN" <<'PY'
import re, sys
path, lan = sys.argv[1:3]
text = open(path, encoding='utf-8').read()
text2, n = re.subn(r'^(\s*host\s*=\s*)100\.\d+\.\d+\.\d+\s*$', rf'\g<1>{lan}', text, flags=re.M)
if n:
    open(path, 'w', encoding='utf-8').write(text2)
    print(f'    rclone: {n} host 100.x -> {lan}')
else:
    print('    rclone: không còn host 100.x (giữ nguyên)')
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

disable_tailscale() {
  if ! command -v tailscale >/dev/null 2>&1 && ! systemctl list-unit-files tailscaled.service >/dev/null 2>&1; then
    log "    tailscale chưa cài — bỏ qua"
    return 0
  fi
  log "==> Tắt Tailscale"
  tailscale down 2>/dev/null || true
  systemctl disable --now tailscaled 2>/dev/null || true
  delete_rule "from ${TS_CIDR} to any port 22 proto tcp"
  log "    tailscaled đã tắt. Gỡ hẳn: apt-get remove -y tailscale"
}

cmd_status() {
  local ts="off"
  if systemctl is-active --quiet tailscaled 2>/dev/null; then
    ts="on"
  fi
  local dsm=""
  if [[ -f "$ENV_FILE" ]]; then
    dsm="$(grep -E '^NAS_DSM_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  fi
  echo "mode_file=$([[ -f "$STATE_FILE" ]] && tr -d '[:space:]' < "$STATE_FILE" || echo unknown)"
  echo "tailscale=${ts}"
  echo "nas_dsm_url=${dsm}"
  echo "nas_lan=${NAS_LAN}"
  echo "fortigate_wan=${FORTIGATE_WAN}"
  echo "lan_445=$(tcp_open "$NAS_LAN" 445 && echo open || echo closed)"
  echo "lan_5556=$(tcp_open "$NAS_LAN" 5556 && echo open || echo closed)"
}

cmd_apply() {
  log "==> NAS qua VPN site-to-site (${NAS_LAN})"
  if ! tcp_open "$NAS_LAN" 445 && ! tcp_open "$NAS_LAN" 5556; then
    echo "ERROR: NAS LAN ${NAS_LAN} chưa thông (445/5556). Kiểm tra tunnel IPsec."
    exit 1
  fi
  ensure_rule "from ${FORTIGATE_WAN} to any port 22 proto tcp" "SSH Fortinet WAN"
  ensure_rule "from ${FORTIGATE_WAN} to any port 500 proto udp" "IPsec IKE"
  ensure_rule "from ${FORTIGATE_WAN} to any port 4500 proto udp" "IPsec NAT-T"
  rewrite_nas_hosts
  write_state site-to-site
  if [[ "$DISABLE_TS" == "1" ]]; then
    disable_tailscale
  fi
  recreate_app
  log "    NAS đi ${NAS_LAN} qua VPN site-to-site."
}

case "$MODE" in
  status) cmd_status ;;
  apply) cmd_apply ;;
  *)
    echo "Usage: $0 status|apply"
    exit 2
    ;;
esac
