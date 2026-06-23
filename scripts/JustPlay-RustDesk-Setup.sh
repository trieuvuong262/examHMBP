#!/usr/bin/env bash
# JustPlay - Cai RustDesk + dang ky Portal (Linux Mint / Ubuntu / Debian)
# Chay trong terminal: chmod +x JustPlay-RustDesk-Setup.sh && sudo ./JustPlay-RustDesk-Setup.sh

echo '========================================'
echo ' JustPlay - Cai dat RustDesk (Linux)'
echo '========================================'
echo ''

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo 'Can quyen root. Dang chay lai voi sudo...'
  echo '(Neu hoi mat khau, nhap mat khau may tinh)'
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
  INSTALLER_URL='https://github.com/rustdesk/rustdesk/releases/download/1.3.9/rustdesk-1.3.9-x86_64.deb'
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

install_rustdesk() {
  echo '[1/5] Tai RustDesk (.deb)...'
  local deb="/tmp/justplay-rustdesk.deb"
  curl -fsSL "$INSTALLER_URL" -o "$deb"
  echo '[2/5] Cai dat...'
  apt-get install -y -qq ./"$deb" 2>/dev/null || dpkg -i "$deb" || apt-get install -f -y -qq
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
  if systemctl list-unit-files 'rustdesk.service' &>/dev/null 2>&1; then
    mkdir -p "$root_cfg"
    cp "$toml_path" "${root_cfg}/RustDesk2.toml"
    echo "      Da ghi them: ${root_cfg}/RustDesk2.toml (systemd)"
  fi
  local bin
  bin="$(find_rustdesk_bin)"
  if [[ -n "$bin" ]]; then
    local b64
    b64="$(python3 -c "import base64, pathlib; print(base64.b64encode(pathlib.Path('${toml_path}').read_bytes()).decode())")"
    run_as_user "$bin" --config "$b64" 2>/dev/null || true
    "$bin" --config "$b64" 2>/dev/null || true
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
    systemctl restart rustdesk 2>/dev/null || true
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
    id="$(run_as_user "$bin" --get-id 2>/dev/null | tr -cd '0-9')"
    if [[ "$id" =~ ^[0-9]{6,12}$ ]]; then
      echo "$id"
      return 0
    fi
  fi
  for f in "${CONFIG_DIR}/RustDesk.toml" "${CONFIG_DIR}/RustDesk2.toml"; do
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
Comment=JustPlay remote desktop
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
  echo '[5/5] Dang ky len Portal...'
  payload="$(
    export JP_ENROLL="$ENROLL_SECRET"
    export JP_RD_ID="$rd_id"
    export JP_PW="$CLIENT_PASSWORD"
    export JP_HOST="$hostname"
    export JP_IP="$ip"
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
if assigned:
    data['assigned_user_text'] = assigned
if dept:
    data['department_text'] = dept
print(json.dumps(data))
PY
  )"
  http_code="$(curl -sS -o /tmp/justplay-rustdesk-enroll.json -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json; charset=utf-8' \
    -H 'User-Agent: JustPlay-RustDesk-Setup/1.0' \
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

BIN="$(find_rustdesk_bin)"
if [[ -z "$BIN" ]]; then
  install_rustdesk
  BIN="$(find_rustdesk_bin)"
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
    start_rustdesk
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
echo ' THANH CONG'
echo " RustDesk ID: $RD_ID"
echo " Portal: $RESP"
echo ' IT co the ket noi tai Quan tri -> RustDesk'
echo '========================================'
read -r -p 'Nhan Enter de thoat...' _ || true
