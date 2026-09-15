#!/usr/bin/env bash
# Công tắc đường admin VPS: Fortinet (WAN văn phòng) <-> Tailscale.
# IPsec NAS (strongSwan) không tắt — chỉ siết UDP 500/4500 về IP Fortigate.
#
#   bash scripts/vps-remote-access-mode.sh status
#   bash scripts/vps-remote-access-mode.sh fortinet
#   bash scripts/vps-remote-access-mode.sh tailscale
#
# Portal gọi cùng script qua Docker nsenter (PID 1).
set -euo pipefail

MODE="${1:-status}"
FORTIGATE_WAN="${FORTIGATE_WAN_IP:-14.161.25.119}"
TS_CIDR="100.64.0.0/10"
STATE_DIR="/etc/portaljustplay"
STATE_FILE="${STATE_DIR}/remote-access.mode"

log() { echo "$@"; }

ensure_ufw() {
  if ! command -v ufw >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ufw
  fi
  ufw default deny incoming >/dev/null 2>&1 || true
  ufw default allow outgoing >/dev/null 2>&1 || true
  ufw allow 80/tcp comment 'HTTP' >/dev/null 2>&1 || true
  ufw allow 443/tcp comment 'HTTPS' >/dev/null 2>&1 || true
}

ensure_rule() {
  local spec="$1"
  local comment="$2"
  if ufw status 2>/dev/null | grep -Fq "$spec"; then
    log "    giữ: $spec"
    return 0
  fi
  ufw allow $spec comment "$comment" >/dev/null
  log "    + ufw allow $spec"
}

delete_matching_ssh_or_ike() {
  local needle="$1"
  local pass=0
  while [[ $pass -lt 12 ]]; do
    local line num
    line="$(ufw status numbered 2>/dev/null | grep -F "$needle" | head -1 || true)"
    [[ -z "$line" ]] && break
    num="$(echo "$line" | sed -n 's/^\[\s*\([0-9]\+\)\].*/\1/p')"
    [[ -z "$num" ]] && break
    ufw --force delete "$num" >/dev/null
    log "    - ufw delete #$num ($needle)"
    pass=$((pass + 1))
  done
}

write_state() {
  mkdir -p "$STATE_DIR"
  echo "$1" > "$STATE_FILE"
  chmod 644 "$STATE_FILE"
}

cmd_status() {
  local file_mode="unknown"
  [[ -f "$STATE_FILE" ]] && file_mode="$(tr -d '[:space:]' < "$STATE_FILE")"
  local ts="off"
  if systemctl is-active --quiet tailscaled 2>/dev/null; then
    ts="on"
  fi
  echo "mode_file=${file_mode}"
  echo "tailscale=${ts}"
  echo "fortigate_wan=${FORTIGATE_WAN}"
  echo "ssh_wan=$(ufw status 2>/dev/null | grep -F "$FORTIGATE_WAN" | grep -c '22' || true)"
  echo "ssh_tailscale=$(ufw status 2>/dev/null | grep -F "$TS_CIDR" | grep -c '22' || true)"
  if command -v tailscale >/dev/null 2>&1; then
    tailscale status --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('tailscale_self='+d.get('Self',{}).get('DNSName',''))" 2>/dev/null || true
  fi
}

cmd_fortinet() {
  log "==> Chế độ Fortinet: SSH chỉ WAN văn phòng, tắt Tailscale"
  log "    Fortigate WAN: ${FORTIGATE_WAN}"
  ensure_ufw
  # 1) Mở SSH WAN trước — tránh tự khóa nếu đang SSH qua Tailscale
  ensure_rule "from ${FORTIGATE_WAN} to any port 22 proto tcp" "SSH Fortinet WAN"
  ensure_rule "from ${FORTIGATE_WAN} to any port 500 proto udp" "IPsec IKE"
  ensure_rule "from ${FORTIGATE_WAN} to any port 4500 proto udp" "IPsec NAT-T"
  delete_matching_ssh_or_ike "22/tcp                     ALLOW IN    Anywhere"
  delete_matching_ssh_or_ike "500/udp                    ALLOW IN    Anywhere"
  delete_matching_ssh_or_ike "4500/udp                   ALLOW IN    Anywhere"
  delete_matching_ssh_or_ike "500/udp (v6)"
  delete_matching_ssh_or_ike "4500/udp (v6)"
  delete_matching_ssh_or_ike "${TS_CIDR}"
  if ! ufw status | grep -qi 'Status: active'; then
    ufw --force enable
  fi
  ufw reload >/dev/null 2>&1 || true
  if ! ufw status | grep -F "${FORTIGATE_WAN}" | grep -q '22'; then
    echo "ERROR: Chưa có rule SSH từ ${FORTIGATE_WAN} — hủy, không tắt Tailscale."
    exit 1
  fi
  systemctl disable --now tailscaled
  write_state fortinet
  log "    Tailscale đã tắt. IPsec NAS giữ nguyên."
  ufw status | grep -E '22|500|4500|Status' || true
}

cmd_tailscale() {
  log "==> Chế độ Tailscale: bật mesh + SSH từ 100.64.0.0/10 (giữ SSH WAN)"
  ensure_ufw
  ensure_rule "from ${FORTIGATE_WAN} to any port 22 proto tcp" "SSH Fortinet WAN"
  systemctl enable --now tailscaled
  if command -v tailscale >/dev/null 2>&1; then
    tailscale up --timeout=25s || log "    WARN: tailscale up chưa xong — kiểm tra sau."
  fi
  ensure_rule "from ${TS_CIDR} to any port 22 proto tcp" "SSH Tailscale"
  if ! ufw status | grep -qi 'Status: active'; then
    ufw --force enable
  fi
  ufw reload >/dev/null 2>&1 || true
  write_state tailscale
  log "    Tailscale đã bật. SSH WAN văn phòng vẫn giữ."
  ufw status | grep -E '22|Status' || true
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
