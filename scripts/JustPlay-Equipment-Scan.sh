#!/usr/bin/env bash
# JustPlay - Quet cau hinh may + dang ky Quan ly thiet bi IT (Ubuntu 26.04 / Linux)
# Dong bo muc dich voi JustPlay-Equipment-Scan.ps1 (Windows) — khong sua file Windows.
# Chay: chmod +x JustPlay-Equipment-Scan.sh && ./JustPlay-Equipment-Scan.sh

echo '========================================'
echo ' JustPlay - Them cau hinh (Ubuntu)'
echo '========================================'
echo ''

set -euo pipefail

PORTAL_URL='__PORTAL_URL__'
SCAN_SECRET='__SCAN_SECRET__'
ASSIGNED_USER_TEXT='__ASSIGNED_USER_TEXT__'
DEPARTMENT_TEXT='__DEPARTMENT_TEXT__'

if [[ "$PORTAL_URL" == *'__PORTAL'* ]]; then
  PORTAL_URL='https://portal.justplay.vn'
fi
if [[ "$SCAN_SECRET" == *'__SCAN'* ]]; then
  echo 'LOI: Chua cau hinh SCAN SECRET. Tai file tu Portal.' >&2
  exit 1
fi
if [[ "$ASSIGNED_USER_TEXT" == *'__ASSIGNED'* ]]; then
  ASSIGNED_USER_TEXT=''
fi
if [[ "$DEPARTMENT_TEXT" == *'__DEPARTMENT'* ]]; then
  DEPARTMENT_TEXT=''
fi

is_lan_ip() {
  local ip="$1"
  [[ -z "$ip" ]] && return 1
  [[ "$ip" == 127.* ]] && return 1
  [[ "$ip" == 169.254.* ]] && return 1
  [[ "$ip" == 192.168.65.* ]] && return 1
  [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[01])\. ]] && return 1
  return 0
}

get_primary_lan_ip() {
  local line iface ip
  while IFS= read -r line; do
    if [[ "$line" =~ ^[0-9]+:\ ([^:]+): ]]; then
      iface="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ inet\ ([0-9.]+)/ ]]; then
      ip="${BASH_REMATCH[1]}"
      [[ "$iface" == lo ]] && continue
      [[ "$iface" == docker* || "$iface" == br-* || "$iface" == veth* || "$iface" == virbr* ]] && continue
      if is_lan_ip "$ip"; then
        echo "$ip"
        return 0
      fi
    fi
  done < <(ip -o addr show scope global 2>/dev/null || true)

  if command -v hostname >/dev/null 2>&1; then
    for ip in $(hostname -I 2>/dev/null || true); do
      if is_lan_ip "$ip"; then
        echo "$ip"
        return 0
      fi
    done
  fi
  return 1
}

normalize_mac() {
  local raw="$1"
  local hex
  hex="$(echo "$raw" | tr -cd '0-9A-Fa-f')"
  if [[ ${#hex} -ne 12 ]]; then
    return 1
  fi
  printf '%s:%s:%s:%s:%s:%s' \
    "${hex:0:2}" "${hex:2:2}" "${hex:4:2}" \
    "${hex:6:2}" "${hex:8:2}" "${hex:10:2}" | tr 'a-f' 'A-F'
}

get_primary_mac() {
  local line iface mac
  while IFS= read -r line; do
    if [[ "$line" =~ ^[0-9]+:\ ([^:]+): ]]; then
      iface="${BASH_REMATCH[1]}"
      [[ "$iface" == lo ]] && continue
      mac="$(cat "/sys/class/net/${iface}/address" 2>/dev/null || true)"
      if [[ -n "$mac" && "$mac" != "00:00:00:00:00:00" ]]; then
        normalize_mac "$mac" && return 0
      fi
    fi
  done < <(ip -o link show 2>/dev/null || true)

  if command -v ip >/dev/null 2>&1; then
    mac="$(ip link 2>/dev/null | awk '/link\/ether/ {print $2; exit}')"
    if [[ -n "$mac" ]]; then
      normalize_mac "$mac" && return 0
    fi
  fi
  return 1
}

collect_inventory_json() {
  local primary_mac="$1"
  local hostname ip os_name os_version os_build os_arch
  local manufacturer model serial cpu ram_gb storage gpu logged_in rustdesk_id
  local network_adapters chassis_type

  hostname="$(hostname -s 2>/dev/null || hostname)"
  ip="$(get_primary_lan_ip 2>/dev/null || true)"
  os_name=''
  os_version=''
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    os_name="${PRETTY_NAME:-$NAME}"
    os_version="${VERSION_ID:-}"
  fi
  os_build="$(uname -r 2>/dev/null || true)"
  os_arch="$(uname -m 2>/dev/null || true)"

  if command -v dmidecode >/dev/null 2>&1; then
    manufacturer="$(dmidecode -s system-manufacturer 2>/dev/null | head -n1 || true)"
    model="$(dmidecode -s system-product-name 2>/dev/null | head -n1 || true)"
    serial="$(dmidecode -s system-serial-number 2>/dev/null | head -n1 || true)"
    chassis_type="$(dmidecode -s chassis-type 2>/dev/null | head -n1 || true)"
  fi

  if command -v lscpu >/dev/null 2>&1; then
    cpu="$(lscpu 2>/dev/null | awk -F: '/Model name/ {gsub(/^ +/,"",$2); print $2; exit}')"
  fi

  if command -v free >/dev/null 2>&1; then
    ram_gb="$(free -g 2>/dev/null | awk '/^Mem:/ {print $2}')"
  fi

  if command -v lsblk >/dev/null 2>&1; then
    storage="$(lsblk -dn -o NAME,SIZE,TYPE,MODEL 2>/dev/null | tr '\n' '; ')"
  fi

  if command -v lspci >/dev/null 2>&1; then
    gpu="$(lspci 2>/dev/null | grep -iE 'vga|3d|display' | head -n2 | tr '\n' '; ')"
  fi

  logged_in="${SUDO_USER:-${USER:-}}"
  network_adapters="$(ip -o link 2>/dev/null | awk '/link\/ether/ {print $2"="$5}' | tr '\n' ', ')"

  if command -v rustdesk >/dev/null 2>&1; then
    rustdesk_id="$(rustdesk --get-id 2>/dev/null | tr -cd '0-9' || true)"
  fi

  SCAN_SECRET="$SCAN_SECRET" \
  JP_MAC="$primary_mac" \
  JP_HOST="$hostname" \
  JP_IP="$ip" \
  JP_MAN="${manufacturer:-}" \
  JP_MODEL="${model:-}" \
  JP_SERIAL="${serial:-}" \
  JP_CHASSIS="${chassis_type:-}" \
  JP_OS_NAME="${os_name:-}" \
  JP_OS_VER="${os_version:-}" \
  JP_OS_BUILD="${os_build:-}" \
  JP_OS_ARCH="${os_arch:-}" \
  JP_CPU="${cpu:-}" \
  JP_RAM="${ram_gb:-}" \
  JP_STORAGE="${storage:-}" \
  JP_GPU="${gpu:-}" \
  JP_LOGGED="${logged_in:-}" \
  JP_RD="${rustdesk_id:-}" \
  JP_NET="${network_adapters:-}" \
  JP_ASSIGNED="$ASSIGNED_USER_TEXT" \
  JP_DEPT="$DEPARTMENT_TEXT" \
  python3 - <<'PY'
import json, os

def s(key, default=''):
    return (os.environ.get(key) or default).strip()

payload = {
    'scan_secret': s('SCAN_SECRET'),
    'mac_address': s('JP_MAC'),
    'hostname': s('JP_HOST'),
    'computer_name': s('JP_HOST'),
    'ip_address': s('JP_IP'),
    'manufacturer': s('JP_MAN'),
    'model': s('JP_MODEL'),
    'model_number': s('JP_MODEL'),
    'serial_number': s('JP_SERIAL'),
    'bios_serial': s('JP_SERIAL'),
    'chassis_type': s('JP_CHASSIS'),
    'os_name': s('JP_OS_NAME'),
    'os_version': s('JP_OS_VER'),
    'os_build': s('JP_OS_BUILD'),
    'os_arch': s('JP_OS_ARCH'),
    'cpu': s('JP_CPU'),
    'ram_gb': s('JP_RAM') or None,
    'storage': s('JP_STORAGE'),
    'gpu': s('JP_GPU'),
    'logged_in_user': s('JP_LOGGED'),
    'rustdesk_id': s('JP_RD') or None,
    'assigned_user_text': s('JP_ASSIGNED'),
    'department_text': s('JP_DEPT'),
    'platform': 'linux',
    'network_adapters': s('JP_NET'),
    'mac_addresses': s('JP_NET'),
}
print(json.dumps(payload, ensure_ascii=False))
PY
}

api_post() {
  local path="$1"
  local payload="$2"
  curl -fsSL -X POST \
    -H 'Content-Type: application/json; charset=utf-8' \
    -d "$payload" \
    "${PORTAL_URL%/}${path}"
}

PRIMARY_MAC="$(get_primary_mac || true)"
if [[ -z "$PRIMARY_MAC" ]]; then
  echo 'LOI: Khong doc duoc dia chi MAC.' >&2
  exit 1
fi
echo "MAC chinh: $PRIMARY_MAC"

echo '[1/3] Kiem tra MAC tren Portal...'
CHECK_PAYLOAD="$(python3 -c "import json; print(json.dumps({'scan_secret': '''$SCAN_SECRET''', 'mac_address': '''$PRIMARY_MAC'''}))")"
CHECK_RESP="$(api_post '/thiet-bi/api/quyet-cau-hinh/kiem-tra/' "$CHECK_PAYLOAD")"
if echo "$CHECK_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('exists') else 1)"; then
  CODE="$(echo "$CHECK_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('device_code',''))")"
  echo "      Da co thiet bi: $CODE — khong gui lai."
  echo '========================================'
  exit 0
fi

echo '[2/3] Thu thap cau hinh may...'
PAYLOAD="$(collect_inventory_json "$PRIMARY_MAC")"
echo "      Hostname: $(hostname -s 2>/dev/null || hostname)"
echo "      OS: $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"

echo '[3/3] Gui len Portal (Quan ly thiet bi IT)...'
RESP="$(api_post '/thiet-bi/api/quyet-cau-hinh/' "$PAYLOAD")"
STATUS="$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")"
if [[ "$STATUS" == 'skipped' ]]; then
  echo '      Bo qua: MAC da co tren Portal.'
  exit 0
fi
if [[ "$STATUS" != 'success' ]]; then
  echo "LOI: $RESP" >&2
  exit 1
fi

CODE="$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('device_code',''))")"
NAME="$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('name',''))")"
echo ''
echo '========================================'
echo ' THANH CONG'
echo " Ma thiet bi: $CODE"
echo " Ten: $NAME"
echo ' IT xem tai Quan ly thiet bi -> Danh sach IT'
echo '========================================'
