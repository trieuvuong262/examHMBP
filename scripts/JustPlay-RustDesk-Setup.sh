#!/usr/bin/env bash
# JustPlay — Cài RustDesk + đăng ký Portal (Linux Mint / Ubuntu / Debian)
# Chạy: chmod +x JustPlay-RustDesk-Setup.sh && sudo ./JustPlay-RustDesk-Setup.sh

set -euo pipefail

PORTAL_URL='__PORTAL_URL__'
RUSTDESK_HOST='__RUSTDESK_HOST__'
PUBLIC_KEY='__PUBLIC_KEY__'
CLIENT_PASSWORD='__CLIENT_PASSWORD__'
ENROLL_SECRET='__ENROLL_SECRET__'
INSTALLER_URL='__INSTALLER_URL_LINUX__'

if [[ "$PORTAL_URL" == *'__PORTAL'* ]]; then
  PORTAL_URL='https://portal.justplay.vn'
fi
if [[ "$RUSTDESK_HOST" == *'__RUSTDESK'* ]]; then
  RUSTDESK_HOST='rd.justplay.vn'
fi
if [[ "$PUBLIC_KEY" == *'__PUBLIC'* ]]; then
  echo 'LOI: Chưa cấu hình PUBLIC KEY. Tải file từ Portal.' >&2
  exit 1
fi
if [[ "$ENROLL_SECRET" == *'__ENROLL'* ]]; then
  echo 'LOI: Chưa cấu hình ENROLL SECRET. Tải file từ Portal.' >&2
  exit 1
fi
if [[ -z "$INSTALLER_URL" || "$INSTALLER_URL" == *'__INSTALLER'* ]]; then
  INSTALLER_URL='https://github.com/rustdesk/rustdesk/releases/download/1.3.9/rustdesk-1.3.9-x86_64.deb'
fi
if [[ "$CLIENT_PASSWORD" == *'__CLIENT'* ]]; then
  CLIENT_PASSWORD=''
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo 'Cần quyền root: sudo ./JustPlay-RustDesk-Setup.sh' >&2
  exit 1
fi

CONFIG_DIR="${HOME}/.config/rustdesk"
if [[ -n "${SUDO_USER:-}" ]]; then
  CONFIG_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.config/rustdesk"
fi

find_rustdesk_bin() {
  command -v rustdesk 2>/dev/null || true
}

install_rustdesk() {
  echo '[1/5] Tải RustDesk (.deb)...'
  local deb="/tmp/justplay-rustdesk.deb"
  curl -fsSL "$INSTALLER_URL" -o "$deb"
  echo '[2/5] Cài đặt...'
  apt-get install -y -qq ./"$deb" 2>/dev/null || dpkg -i "$deb" || apt-get install -f -y -qq
  rm -f "$deb"
}

write_server_config() {
  echo "[3/5] Cấu hình server ${RUSTDESK_HOST}..."
  mkdir -p "$CONFIG_DIR"
  cat > "${CONFIG_DIR}/RustDesk2.toml" <<EOF
[options]
custom-rendezvous-server = '${RUSTDESK_HOST}'
relay-server = '${RUSTDESK_HOST}'
api-server = ''
key = '${PUBLIC_KEY}'
EOF
  chown -R "${SUDO_USER:-root}:${SUDO_USER:-root}" "$(dirname "$CONFIG_DIR")" 2>/dev/null || true
}

stop_rustdesk() {
  pkill -x rustdesk 2>/dev/null || true
  sleep 2
}

start_rustdesk() {
  local bin
  bin="$(find_rustdesk_bin)"
  if [[ -n "$bin" ]]; then
    if [[ -n "${SUDO_USER:-}" ]]; then
      sudo -u "$SUDO_USER" "$bin" &>/dev/null &
    else
      "$bin" &>/dev/null &
    fi
    sleep 6
  fi
}

get_rustdesk_id() {
  local f
  for f in "${CONFIG_DIR}/RustDesk.toml" "${CONFIG_DIR}/RustDesk2.toml"; do
    if [[ -f "$f" ]]; then
      local id
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
  if [[ -z "$CLIENT_PASSWORD" ]]; then
    return 0
  fi
  if [[ -n "${SUDO_USER:-}" ]]; then
    sudo -u "$SUDO_USER" "$bin" --password "$CLIENT_PASSWORD" &>/dev/null || true
  else
    "$bin" --password "$CLIENT_PASSWORD" &>/dev/null || true
  fi
  sleep 2
}

register_portal() {
  local rd_id="$1"
  local hostname ip payload
  hostname="$(hostname -s 2>/dev/null || hostname)"
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo '[5/5] Đăng ký lên Portal...'
  payload=$(printf '{"enroll_secret":"%s","rustdesk_id":"%s","rustdesk_password":"%s","hostname":"%s","ip_address":"%s","name":"%s"}' \
    "$ENROLL_SECRET" "$rd_id" "$CLIENT_PASSWORD" "$hostname" "$ip" "$hostname")
  curl -fsSL -X POST \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "${PORTAL_URL%/}/nhat-ky/rustdesk/api/dang-ky/"
}

echo '========================================'
echo ' JustPlay — Cài đặt RustDesk (Linux)'
echo '========================================'

BIN="$(find_rustdesk_bin)"
if [[ -z "$BIN" ]]; then
  install_rustdesk
  BIN="$(find_rustdesk_bin)"
fi
if [[ -z "$BIN" ]]; then
  echo 'Không tìm thấy rustdesk sau khi cài.' >&2
  exit 1
fi

stop_rustdesk
write_server_config
start_rustdesk
set_password "$BIN"

echo '[4/5] Đọc RustDesk ID...'
RD_ID=''
for _ in $(seq 1 12); do
  if RD_ID="$(get_rustdesk_id)"; then
    break
  fi
  sleep 3
  start_rustdesk
done
if [[ -z "$RD_ID" ]]; then
  echo 'Không đọc được RustDesk ID. Mở RustDesk, kiểm tra kết nối server rồi chạy lại.' >&2
  exit 1
fi
echo "      ID: $RD_ID"

RESP="$(register_portal "$RD_ID")"
echo ''
echo '========================================'
echo ' THÀNH CÔNG'
echo " RustDesk ID: $RD_ID"
echo " Portal: $RESP"
echo ' IT có thể kết nối tại Quản trị → RustDesk'
echo '========================================'
