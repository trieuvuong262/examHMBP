#!/usr/bin/env bash
# JustPlay - Cai RaiDrive CLI tren Ubuntu 26.04 LTS (Ubuntu 20.04+)
# Chay: chmod +x JustPlay-RaiDrive-Setup.sh && sudo ./JustPlay-RaiDrive-Setup.sh
# Neu tai .deb bi chan: script mo https://www.raidrive.com/download/linux

echo '========================================'
echo ' JustPlay - Cai RaiDrive (Ubuntu)'
echo '========================================'
echo ''

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo 'Can quyen root. Dang chay lai voi sudo...'
  exec sudo -E bash "$0" "$@"
fi

set -euo pipefail

INSTALLER_URL='__RAIDRIVE_INSTALLER_URL_LINUX__'
DOWNLOAD_PAGE='https://www.raidrive.com/download/linux'
DEFAULT_AMD64='https://app.raidrive.com/deb/raidrive-2025.12.0-linux.amd64.deb'
DEFAULT_ARM64='https://app.raidrive.com/deb/raidrive-2025.12.0-linux.arm64.deb'

if [[ -z "$INSTALLER_URL" || "$INSTALLER_URL" == *'__RAIDRIVE'* ]]; then
  case "$(uname -m)" in
    aarch64|arm64) INSTALLER_URL="$DEFAULT_ARM64" ;;
    *) INSTALLER_URL="$DEFAULT_AMD64" ;;
  esac
fi

echo "      He: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-Linux}")"
echo "      Arch: $(uname -m)"
echo ''

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq curl ca-certificates xdg-utils >/dev/null 2>&1 || \
  apt-get install -y curl ca-certificates || true

DEB="/tmp/justplay-raidrive.deb"
rm -f "$DEB"

echo '[1/2] Tai RaiDrive CLI (.deb)...'
echo "      URL: $INSTALLER_URL"
if ! curl -fL --retry 2 --retry-delay 2 \
  -A 'Mozilla/5.0 (X11; Linux x86_64) JustPlay-RaiDrive-Setup' \
  -e 'https://www.raidrive.com/download/linux' \
  "$INSTALLER_URL" -o "$DEB" 2>/tmp/justplay-raidrive-curl.err; then
  echo '      Khong tai duoc .deb tu CDN (co the bi chan).'
  echo "      Mo trang tai: $DOWNLOAD_PAGE"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$DOWNLOAD_PAGE" >/dev/null 2>&1 || true
  fi
  echo ''
  echo 'Sau khi tai file .deb (amd64/arm64), chay:'
  echo '  sudo apt install -fy ./raidrive-*-linux.*.deb'
  read -r -p 'Nhan Enter de thoat...' _ || true
  exit 1
fi

if [[ ! -s "$DEB" ]]; then
  echo 'LOI: File .deb rong.' >&2
  exit 1
fi

echo '[2/2] Cai dat (apt install -fy)...'
apt-get install -y -f "$DEB"
rm -f "$DEB"

echo ''
if command -v raidrivecli >/dev/null 2>&1; then
  echo ' THANH CONG — RaiDrive CLI da cai'
  raidrivecli status 2>/dev/null || true
  echo ''
  echo ' Goi y WebDAV JustPlay:'
  echo '   raidrivecli add webdav https://justplay.synology.me:5678 -l JustPlay -u USER -p'
  echo ' (USER / mat khau = tai khoan Portal)'
else
  echo ' Cai xong nhung khong thay lenh raidrivecli.'
fi
echo '========================================'
read -r -p 'Nhan Enter de thoat...' _ || true
