#!/usr/bin/env bash
# JustPlay - Cai RustDesk + dang ky Portal cho Ubuntu 26.04 LTS (vd. 26.04.1)
# Dong bo luong voi JustPlay-RustDesk-Setup.ps1 (Windows) — khong sua file Windows.
# Chay: chmod +x JustPlay-RustDesk-Setup.sh && sudo ./JustPlay-RustDesk-Setup.sh

echo '========================================'
echo ' JustPlay - Cai RustDesk (Ubuntu 26.04)'
echo '========================================'
echo ''

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo 'Can quyen root. Dang chay lai voi sudo...'
  echo '(Neu hoi mat khau, nhap mat khau may tinh Ubuntu)'
  echo ''
  exec sudo -E bash "$0" "$@"
fi

set -euo pipefail

PORTAL_URL='__PORTAL_URL__'
RUSTDESK_HOST='__RUSTDESK_HOST__'
PUBLIC_KEY='__PUBLIC_KEY__'
CLIENT_PASSWORD='__CLIENT_PASSWORD__'
ENROLL_SECRET='__ENROLL_SECRET__'
APPROVE_MODE='__RUSTDESK_APPROVE_MODE__'
INSTALLER_URL='__INSTALLER_URL_LINUX__'
ASSIGNED_USER_TEXT='__ASSIGNED_USER_TEXT__'
DEPARTMENT_TEXT='__DEPARTMENT_TEXT__'

# Mac dinh .deb da kiem thu tren Ubuntu 26.04 LTS (amd64)
DEFAULT_DEB_URL='https://github.com/rustdesk/rustdesk/releases/download/1.4.6/rustdesk-1.4.6-x86_64.deb'

if [[ "$PORTAL_URL" == *'__PORTAL'* ]]; then
  PORTAL_URL='https://portal.justplay.vn'
fi
if [[ "$RUSTDESK_HOST" == *'__RUSTDESK'* ]]; then
  RUSTDESK_HOST='rd.justplay.vn'
fi
if [[ "$PUBLIC_KEY" == *'__PUBLIC'* ]]; then
  echo 'LOI: Chua cau hinh PUBLIC KEY. Tai file tu Portal.' >&2
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
fi
if [[ "$ENROLL_SECRET" == *'__ENROLL'* ]]; then
  echo 'LOI: Chua cau hinh ENROLL SECRET. Tai file tu Portal.' >&2
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
fi
if [[ -z "$INSTALLER_URL" || "$INSTALLER_URL" == *'__INSTALLER'* ]]; then
  INSTALLER_URL="$DEFAULT_DEB_URL"
fi
if [[ "$CLIENT_PASSWORD" == *'__CLIENT'* ]]; then
  CLIENT_PASSWORD=''
fi
if [[ "$APPROVE_MODE" == *'__RUSTDESK'* || -z "$APPROVE_MODE" ]]; then
  APPROVE_MODE='password'
fi
if [[ "$ASSIGNED_USER_TEXT" == *'__ASSIGNED'* ]]; then
  ASSIGNED_USER_TEXT=''
fi
if [[ "$DEPARTMENT_TEXT" == *'__DEPARTMENT'* ]]; then
  DEPARTMENT_TEXT=''
fi

check_ubuntu_26() {
  if [[ ! -f /etc/os-release ]]; then
    echo 'Canh bao: Khong doc duoc /etc/os-release — tiep tuc (Ubuntu 26.04 khuyen nghi).'
    return 0
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  local id_l="${ID:-}"
  local ver="${VERSION_ID:-}"
  local like="${ID_LIKE:-}"
  echo "      He dieu hanh: ${PRETTY_NAME:-$NAME $ver}"
  if [[ "$id_l" != "ubuntu" && " $like " != *" ubuntu "* && " $like " != *" debian "* ]]; then
    echo "LOI: Script nay danh cho Ubuntu 26.04 LTS (deb). Hien tai: ${PRETTY_NAME:-unknown}" >&2
    read -r -p 'Nhan Enter de thoat...' _ || true
    exit 1
  fi
  if [[ "$id_l" == "ubuntu" && -n "$ver" ]]; then
    local major="${ver%%.*}"
    if [[ "$major" -lt 24 ]]; then
      echo "Canh bao: Ubuntu $ver — da thiet ke cho 26.04.1 LTS; van thu cai..."
    elif [[ "$major" -eq 26 ]]; then
      echo "      OK: Ubuntu $ver (muc tieu 26.04 LTS)"
    else
      echo "      Ubuntu $ver — tiep tuc cai .deb"
    fi
  fi
}

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

get_primary_mac() {
  local line iface mac
  while IFS= read -r line; do
    if [[ "$line" =~ ^[0-9]+:\ ([^:]+): ]]; then
      iface="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ link/ether\ ([0-9a-f:]{17}) ]]; then
      mac="${BASH_REMATCH[1]}"
      [[ "$iface" == lo ]] && continue
      [[ "$iface" == docker* || "$iface" == br-* || "$iface" == veth* || "$iface" == virbr* ]] && continue
      echo "$mac" | tr '[:lower:]' '[:upper:]'
      return 0
    fi
  done < <(ip -o link show 2>/dev/null || true)
  return 1
}

detect_deb_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo 'x86_64' ;;
    aarch64|arm64) echo 'aarch64' ;;
    armv7l|armhf) echo 'armv7' ;;
    *) echo 'x86_64' ;;
  esac
}

resolve_installer_url() {
  if [[ -n "$INSTALLER_URL" && "$INSTALLER_URL" != *'__INSTALLER'* ]]; then
    echo "$INSTALLER_URL"
    return 0
  fi
  local arch tag
  arch="$(detect_deb_arch)"
  tag="$(curl -fsSL https://api.github.com/repos/rustdesk/rustdesk/releases/latest 2>/dev/null \
    | grep -oE '"tag_name":[[:space:]]*"[^"]+"' | head -1 | cut -d'"' -f4 || true)"
  tag="${tag#v}"
  if [[ -n "$tag" ]]; then
    echo "https://github.com/rustdesk/rustdesk/releases/download/${tag}/rustdesk-${tag}-${arch}.deb"
    return 0
  fi
  echo "$DEFAULT_DEB_URL"
}

RUN_USER="${SUDO_USER:-$USER}"
CONFIG_DIR="${HOME}/.config/rustdesk"
if [[ -n "${SUDO_USER:-}" ]]; then
  CONFIG_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.config/rustdesk"
fi

find_rustdesk_bin() {
  command -v rustdesk 2>/dev/null || true
}

run_as_user() {
  if [[ -n "${SUDO_USER:-}" && "$RUN_USER" != "root" ]]; then
    sudo -u "$RUN_USER" "$@"
  else
    "$@"
  fi
}

ensure_apt_tools() {
  echo '[0/5] Kiem tra goi phu thuoc (curl, libxdo3)...'
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq curl ca-certificates libxdo3 >/dev/null 2>&1 || \
    apt-get install -y curl ca-certificates libxdo3 || true
}

install_rustdesk() {
  local url deb
  url="$(resolve_installer_url)"
  INSTALLER_URL="$url"
  echo '[1/5] Tai RustDesk (.deb)...'
  echo "      URL: $url"
  deb="/tmp/justplay-rustdesk.deb"
  rm -f "$deb"
  if ! curl -fL --retry 3 --retry-delay 2 "$url" -o "$deb"; then
    echo "LOI: Tai .deb that bai. Kiem tra mang / RUSTDESK_INSTALLER_URL_LINUX." >&2
    exit 1
  fi
  if [[ ! -s "$deb" ]]; then
    echo 'LOI: File .deb rong.' >&2
    exit 1
  fi
  echo '[2/5] Cai dat (apt install -fy — Ubuntu 26.04)...'
  # Khuyen nghi Ubuntu 26.04: apt install -fy giai quyet phu thuoc tot hon dpkg -i don le
  if ! apt-get install -y -f "$deb"; then
    echo '      Thu lai: dpkg -i + apt-get -f...'
    dpkg -i "$deb" || true
    apt-get install -f -y
  fi
  rm -f "$deb"
}

write_server_config() {
  echo "[3/5] Cau hinh server ${RUSTDESK_HOST}..."
  local toml_path root_cfg="/root/.config/rustdesk"
  mkdir -p "$CONFIG_DIR"
  toml_path="${CONFIG_DIR}/RustDesk2.toml"
  cat > "$toml_path" <<EOF
rendezvous_server = '${RUSTDESK_HOST}:21116'
nat_type = 1
serial = 0

[options]
custom-rendezvous-server = '${RUSTDESK_HOST}'
relay-server = '${RUSTDESK_HOST}:21117'
api-server = ''
key = '${PUBLIC_KEY}'
approve-mode = '${APPROVE_MODE}'
verification-method = 'use-permanent-password'
allow-logon-screen-password = 'Y'
hide-stop-service = 'Y'
EOF
  if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "${SUDO_USER}:${SUDO_USER}" "$(dirname "$CONFIG_DIR")" 2>/dev/null || true
  fi
  # Service chay nhu root — config hieu luc nam o /root/.config/rustdesk
  mkdir -p "$root_cfg"
  cp "$toml_path" "${root_cfg}/RustDesk2.toml"
  echo "      Da ghi: ${root_cfg}/RustDesk2.toml (systemd)"
  local bin
  bin="$(find_rustdesk_bin)"
  if [[ -n "$bin" ]]; then
    local b64
    b64="$(python3 -c "import base64, pathlib; print(base64.b64encode(pathlib.Path('${toml_path}').read_bytes()).decode())")"
    # --config can service dang chay (Ubuntu 26.04)
    systemctl start rustdesk 2>/dev/null || true
    sleep 2
    "$bin" --config "$b64" 2>/dev/null || true
    run_as_user "$bin" --config "$b64" 2>/dev/null || true
  fi
}

stop_rustdesk() {
  pkill -x rustdesk 2>/dev/null || true
  sleep 2
}

start_rustdesk() {
  local bin
  bin="$(find_rustdesk_bin)"
  if [[ -n "$bin" ]]; then
    run_as_user "$bin" &>/dev/null &
    sleep 6
  fi
}

restart_rustdesk() {
  local bin="${1:-$(find_rustdesk_bin)}"
  stop_rustdesk
  if systemctl list-unit-files 'rustdesk.service' &>/dev/null; then
    systemctl enable rustdesk 2>/dev/null || true
    systemctl restart rustdesk 2>/dev/null || systemctl start rustdesk 2>/dev/null || true
    sleep 5
    return
  fi
  if [[ -n "$bin" ]]; then
    start_rustdesk
  fi
}

get_rustdesk_id() {
  local bin id f
  bin="$(find_rustdesk_bin)"
  if [[ -n "$bin" ]]; then
    id="$("$bin" --get-id 2>/dev/null | tr -cd '0-9')"
    if [[ "$id" =~ ^[0-9]{6,12}$ ]]; then
      echo "$id"
      return 0
    fi
    id="$(run_as_user "$bin" --get-id 2>/dev/null | tr -cd '0-9')"
    if [[ "$id" =~ ^[0-9]{6,12}$ ]]; then
      echo "$id"
      return 0
    fi
  fi
  for f in \
    /root/.config/rustdesk/RustDesk.toml \
    /root/.config/rustdesk/RustDesk2.toml \
    "${CONFIG_DIR}/RustDesk.toml" \
    "${CONFIG_DIR}/RustDesk2.toml"
  do
    if [[ -f "$f" ]]; then
      id=$(grep -E "^id\s*=" "$f" | head -1 | sed -E "s/.*['\"]([0-9]+)['\"].*/\1/")
      if [[ -n "$id" ]]; then
        echo "$id"
        return 0
      fi
    fi
  done
  return 1
}

set_password() {
  local bin="$1"
  local root_cfg="/root/.config/rustdesk"
  if [[ -z "$CLIENT_PASSWORD" ]]; then
    echo '      Canh bao: Chua cau hinh RUSTDESK_CLIENT_PASSWORD tren Portal.'
    return 1
  fi
  echo '      Dat mat khau co dinh (can root + service)...'
  systemctl start rustdesk 2>/dev/null || true
  sleep 5
  local out ok=1 attempt
  for attempt in 1 2 3; do
    out="$("$bin" --password "$CLIENT_PASSWORD" 2>&1)" || true
    if [[ "$out" == *Done* ]]; then
      ok=0
      echo '      Mat khau: Done!'
      break
    fi
    echo "      Thu $attempt/3: ${out:-khong co phan hoi}"
    sleep 3
    systemctl restart rustdesk 2>/dev/null || true
    sleep 4
  done
  mkdir -p "$root_cfg"
  for f in RustDesk.toml RustDesk2.toml; do
    if [[ -f "${CONFIG_DIR}/$f" ]]; then
      cp "${CONFIG_DIR}/$f" "${root_cfg}/$f"
    fi
  done
  if [[ -f "${root_cfg}/RustDesk2.toml" ]]; then
    cp "${root_cfg}/RustDesk2.toml" "${CONFIG_DIR}/RustDesk2.toml" 2>/dev/null || true
  fi
  if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "${SUDO_USER}:${SUDO_USER}" "$(dirname "$CONFIG_DIR")" 2>/dev/null || true
  fi
  systemctl restart rustdesk 2>/dev/null || true
  sleep 3
  if [[ "$ok" -ne 0 ]]; then
    echo '      LOI: Khong dat duoc mat khau. Thu tay:'
    echo "        sudo systemctl start rustdesk && sudo rustdesk --password '***'"
    return 1
  fi
  return 0
}

apply_password() {
  local bin="$1"
  restart_rustdesk "$bin"
  set_password "$bin" || true
}

ensure_autostart() {
  local bin="$1"
  echo '[6/6] Kiem tra san sang nhan ket noi...'
  if systemctl list-unit-files 'rustdesk.service' &>/dev/null; then
    systemctl enable rustdesk 2>/dev/null || true
    systemctl start rustdesk 2>/dev/null || true
    echo "      systemd rustdesk: $(systemctl is-active rustdesk 2>/dev/null || echo unknown)"
  fi
  if [[ -n "${SUDO_USER:-}" ]]; then
    local home autostart_dir
    home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    autostart_dir="${home}/.config/autostart"
    mkdir -p "$autostart_dir"
    cat > "${autostart_dir}/rustdesk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RustDesk
Comment=JustPlay remote desktop (Ubuntu)
Exec=${bin}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
    chown "${SUDO_USER}:${SUDO_USER}" "${autostart_dir}/rustdesk.desktop"
  fi
  echo '      Kiem tra: RustDesk -> Network phai Ready (khong Offline).'
}

register_portal() {
  local rd_id="$1"
  local hostname ip payload http_code
  hostname="$(hostname -s 2>/dev/null || hostname)"
  ip="$(get_primary_lan_ip 2>/dev/null || true)"
  mac="$(get_primary_mac 2>/dev/null || true)"
  echo '[5/5] Dang ky len Portal...'
  payload="$(
    export JP_ENROLL="$ENROLL_SECRET"
    export JP_RD_ID="$rd_id"
    export JP_PW="$CLIENT_PASSWORD"
    export JP_HOST="$hostname"
    export JP_IP="$ip"
    export JP_MAC="$mac"
    export JP_NAME="$hostname"
    export JP_ASSIGNED="$ASSIGNED_USER_TEXT"
    export JP_DEPT="$DEPARTMENT_TEXT"
    python3 <<'PY'
import json
import os

data = {
    'enroll_secret': os.environ['JP_ENROLL'],
    'rustdesk_id': os.environ['JP_RD_ID'],
    'rustdesk_password': os.environ['JP_PW'],
    'hostname': os.environ['JP_HOST'],
    'ip_address': os.environ['JP_IP'],
    'name': os.environ['JP_NAME'],
}
assigned = os.environ.get('JP_ASSIGNED', '').strip()
dept = os.environ.get('JP_DEPT', '').strip()
mac = os.environ.get('JP_MAC', '').strip()
if assigned:
    data['assigned_user_text'] = assigned
if dept:
    data['department_text'] = dept
if mac:
    data['mac_address'] = mac
print(json.dumps(data))
PY
  )"
  http_code="$(curl -sS -o /tmp/justplay-rustdesk-enroll.json -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json; charset=utf-8' \
    -H 'User-Agent: JustPlay-RustDesk-Setup-Ubuntu/1.0' \
    -d "$payload" \
    "${PORTAL_URL%/}/nhat-ky/rustdesk/api/dang-ky/")"
  if [[ "$http_code" != '200' ]]; then
    echo "      LOI Portal HTTP $http_code" >&2
    if [[ -f /tmp/justplay-rustdesk-enroll.json ]]; then
      cat /tmp/justplay-rustdesk-enroll.json >&2
      echo >&2
    fi
    return 1
  fi
  cat /tmp/justplay-rustdesk-enroll.json
}

check_ubuntu_26
ensure_apt_tools

BIN="$(find_rustdesk_bin)"
if [[ -z "$BIN" ]]; then
  install_rustdesk
  BIN="$(find_rustdesk_bin)"
else
  echo "      RustDesk da co: $BIN — cap nhat cau hinh JustPlay"
fi
if [[ -z "$BIN" ]]; then
  echo 'Khong tim thay rustdesk sau khi cai.' >&2
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
fi
echo "      Su dung: $BIN"

stop_rustdesk
write_server_config
restart_rustdesk "$BIN"

echo '[4/5] Doc RustDesk ID...'
RD_ID=''
for i in $(seq 1 20); do
  if RD_ID="$(get_rustdesk_id)"; then
    break
  fi
  echo "      Cho RustDesk khoi tao ID... ($i/20)"
  sleep 5
  if (( i % 4 == 0 )); then
    restart_rustdesk "$BIN"
  fi
done
if [[ -z "$RD_ID" ]]; then
  echo "Khong doc duoc RustDesk ID. Kiem tra ket noi ${RUSTDESK_HOST} roi chay lai." >&2
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
fi
echo "      ID: $RD_ID"

echo '[4b/5] Dat mat khau mac dinh...'
apply_password "$BIN"

RESP="$(register_portal "$RD_ID")" || {
  echo 'Dang ky Portal that bai. Kiem tra ENROLL_SECRET va ket noi mang.' >&2
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
}

ensure_autostart "$BIN"

echo ''
echo '========================================'
echo ' THANH CONG (Ubuntu)'
echo " RustDesk ID: $RD_ID"
echo " Portal: $RESP"
echo ' IT co the ket noi tai Quan tri -> RustDesk'
echo '========================================'
read -r -p 'Nhan Enter de thoat...' _ || true
