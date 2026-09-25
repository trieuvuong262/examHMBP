#!/usr/bin/env bash
# Chặn kết nối mới vào VPS từ quốc gia ngoài danh sách cho phép.
# Đặt rule trong ufw-before-input, chỉ trên NIC WAN (mặc định eth0).
# Không đụng Tailscale, Docker bridge, loopback, IPsec đã giải mã.
#
#   bash scripts/vps-geo-access.sh status
#   GEO_BYPASS_IPS=1.2.3.4,5.6.7.8 bash scripts/vps-geo-access.sh apply VN
#   bash scripts/vps-geo-access.sh disable
set -euo pipefail

ACTION="${1:-status}"
COUNTRIES="${2:-VN}"
WAN_IF="${GEO_WAN_IF:-eth0}"
STATE_DIR="/etc/portaljustplay"
STATE_FILE="${STATE_DIR}/geo-access.state"
UFW_BEFORE="/etc/ufw/before.rules"
SET_ALLOW="jp-geo-allow"
SET_ALLOW_TMP="jp-geo-allow-tmp"
SET_BYPASS="jp-geo-bypass"
BEGIN="# jp-geo-begin"
END="# jp-geo-end"
MIN_PREFIXES=50

log() { echo "$@"; }

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: cần root trên host."
    exit 1
  fi
}

ensure_ipset() {
  if command -v ipset >/dev/null 2>&1; then
    return 0
  fi
  log "Cài ipset..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ipset
}

valid_country() {
  [[ "$1" =~ ^[A-Z]{2}$ ]]
}

download_zone() {
  local code="$1"
  local dest="$2"
  local url="https://www.ipdeny.com/ipblocks/data/countries/${code,,}.zone"
  if ! curl -fsSL --retry 2 --max-time 40 "$url" -o "$dest"; then
    echo "ERROR: không tải được dải IP ${code} (${url})"
    exit 1
  fi
  grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$' "$dest" > "${dest}.clean"
  mv "${dest}.clean" "$dest"
  local count
  count="$(wc -l < "$dest" | tr -d ' ')"
  if [[ "$count" -lt "$MIN_PREFIXES" ]]; then
    echo "ERROR: zone ${code} chỉ có ${count} prefix — hủy, không đổi firewall."
    exit 1
  fi
  echo "$count"
}

load_allow_set() {
  local file="$1"
  ipset create "$SET_ALLOW" hash:net family inet maxelem 131072 -exist
  ipset create "$SET_ALLOW_TMP" hash:net family inet maxelem 131072 -exist
  ipset flush "$SET_ALLOW_TMP"
  while read -r cidr; do
    [[ -n "$cidr" ]] || continue
    ipset add "$SET_ALLOW_TMP" "$cidr" -exist
  done < "$file"
  ipset swap "$SET_ALLOW_TMP" "$SET_ALLOW"
  ipset destroy "$SET_ALLOW_TMP" 2>/dev/null || true
}

load_bypass_set() {
  ipset create "$SET_BYPASS" hash:net family inet maxelem 1024 -exist
  ipset flush "$SET_BYPASS"
  local raw="${GEO_BYPASS_IPS:-}"
  raw="${raw//,/ }"
  local token
  for token in $raw; do
    [[ "$token" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
    ipset add "$SET_BYPASS" "${token}/32" -exist
  done
  # Phiên SSH đang dùng để bật rule — portal/nsenter không có biến này.
  local ssh_conn="${SSH_CONNECTION:-}"
  local ssh_ip="${ssh_conn%% *}"
  if [[ "$ssh_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    ipset add "$SET_BYPASS" "${ssh_ip}/32" -exist
  fi
}

write_before_rules() {
  python3 - "$UFW_BEFORE" "$WAN_IF" "$SET_BYPASS" "$SET_ALLOW" "$BEGIN" "$END" <<'PY'
import sys
from pathlib import Path
path, wan, bypass, allow, begin, end = sys.argv[1:]
file = Path(path)
text = file.read_text(encoding="utf-8")
block = "\n".join([
    begin,
    f"-A ufw-before-input -i {wan} -m set --match-set {bypass} src -j ACCEPT",
    f"-A ufw-before-input -i {wan} -m set --match-set {allow} src -j ACCEPT",
    f"-A ufw-before-input -i {wan} -p tcp --dport 80 -j ACCEPT",
    f"-A ufw-before-input -i {wan} -m conntrack --ctstate NEW -j DROP",
    end,
    "",
])
if begin in text and end in text:
    pre, rest = text.split(begin, 1)
    _, post = rest.split(end, 1)
    post = post.lstrip("\n")
    text = pre.rstrip() + "\n" + block + post
else:
    needle = "-A ufw-before-input -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT"
    idx = text.find(needle)
    if idx < 0:
        raise SystemExit("ERROR: không thấy rule ESTABLISHED trong before.rules")
    insert_at = idx + len(needle)
    text = text[:insert_at] + "\n" + block + text[insert_at:]
file.write_text(text, encoding="utf-8")
print("    before.rules đã gắn jp-geo")
PY
}

strip_before_rules() {
  python3 - "$UFW_BEFORE" "$BEGIN" "$END" <<'PY'
import sys
from pathlib import Path
path, begin, end = sys.argv[1:]
file = Path(path)
text = file.read_text(encoding="utf-8")
if begin not in text or end not in text:
    print("    before.rules không có jp-geo")
    raise SystemExit(0)
pre, rest = text.split(begin, 1)
_, post = rest.split(end, 1)
file.write_text(pre.rstrip() + "\n" + post.lstrip("\n"), encoding="utf-8")
print("    đã gỡ jp-geo khỏi before.rules")
PY
}

write_state() {
  mkdir -p "$STATE_DIR"
  cat > "$STATE_FILE" <<EOF
enabled=$1
countries=$2
prefixes=$3
wan_if=$4
applied_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
exempt_tcp80=1
EOF
  chmod 644 "$STATE_FILE"
}

cmd_status() {
  if [[ -f "$STATE_FILE" ]]; then
    cat "$STATE_FILE"
  else
    echo "enabled=0"
    echo "countries="
    echo "prefixes=0"
    echo "wan_if=${WAN_IF}"
  fi
  if command -v ipset >/dev/null 2>&1 && ipset list "$SET_ALLOW" >/dev/null 2>&1; then
    echo "ipset=yes"
  else
    echo "ipset=no"
  fi
}

cmd_apply() {
  need_root
  [[ -f "$UFW_BEFORE" ]] || { echo "ERROR: không thấy ${UFW_BEFORE}"; exit 1; }
  ip link show "$WAN_IF" >/dev/null 2>&1 || { echo "ERROR: không có NIC ${WAN_IF}"; exit 1; }
  ensure_ipset
  local code count total=0 tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  local merged="${tmp}/allow.zone"
  : > "$merged"
  local IFS=','
  for code in $COUNTRIES; do
    code="${code// /}"
    code="${code^^}"
    valid_country "$code" || { echo "ERROR: mã quốc gia không hợp lệ: ${code}"; exit 1; }
    local zone="${tmp}/${code}.zone"
    count="$(download_zone "$code" "$zone")"
    cat "$zone" >> "$merged"
    total=$((total + count))
    log "    ${code}: ${count} prefix"
  done
  unset IFS
  sort -u "$merged" -o "$merged"
  total="$(wc -l < "$merged" | tr -d ' ')"
  load_bypass_set
  load_allow_set "$merged"
  write_before_rules
  write_state 1 "${COUNTRIES^^}" "$total" "$WAN_IF"
  ufw reload >/dev/null
  log "Đã bật chặn quốc gia trên ${WAN_IF}: cho ${COUNTRIES^^} (${total} prefix). TCP/80 vẫn mở để gia hạn chứng chỉ."
}

cmd_disable() {
  need_root
  if [[ -f "$UFW_BEFORE" ]]; then
    strip_before_rules
    ufw reload >/dev/null || true
  fi
  if command -v ipset >/dev/null 2>&1; then
    ipset destroy "$SET_ALLOW_TMP" 2>/dev/null || true
    ipset destroy "$SET_ALLOW" 2>/dev/null || true
    ipset destroy "$SET_BYPASS" 2>/dev/null || true
  fi
  write_state 0 "" 0 "$WAN_IF"
  log "Đã tắt chặn theo quốc gia."
}

case "$ACTION" in
  status) cmd_status ;;
  apply) cmd_apply ;;
  disable) cmd_disable ;;
  *)
    echo "ERROR: lệnh không hợp lệ (status|apply|disable)"
    exit 1
    ;;
esac
