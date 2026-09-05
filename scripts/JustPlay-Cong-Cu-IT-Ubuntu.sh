#!/usr/bin/env bash
# JustPlay Công cụ IT — menu Ubuntu (đi kèm gói .deb)
# Chạy: justplay-cong-cu-it   hoặc   /usr/local/share/justplay-it/JustPlay-Cong-Cu-IT-Ubuntu.sh

set -euo pipefail

SHARE_DIR="${JUSTPLAY_IT_DIR:-/usr/local/share/justplay-it}"
if [[ ! -d "$SHARE_DIR" ]]; then
  SHARE_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

RD="$SHARE_DIR/JustPlay-RustDesk-Setup.sh"
EQ="$SHARE_DIR/JustPlay-Equipment-Scan.sh"
RAI="$SHARE_DIR/JustPlay-RaiDrive-Setup.sh"

run_script() {
  local path="$1"
  local title="$2"
  if [[ ! -f "$path" ]]; then
    zenity --error --title="JustPlay" --text="Thiếu file:\n$path\nTải lại .deb từ Portal." 2>/dev/null \
      || { echo "Thiếu $path"; read -r -p 'Enter...' _; }
    return 1
  fi
  chmod +x "$path" 2>/dev/null || true
  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="$title" -- bash -lc "sudo -E bash '$path'; echo; read -r -p 'Nhan Enter de dong...' _"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -T "$title" -e bash -lc "sudo -E bash '$path'; echo; read -r -p 'Nhan Enter...' _"
  else
    sudo -E bash "$path"
  fi
}

# Equipment scan không bắt buộc sudo
run_equipment() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    zenity --error --text="Thiếu $path" 2>/dev/null || echo "Thiếu $path"
    return 1
  fi
  chmod +x "$path" 2>/dev/null || true
  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="Thêm Cấu hình" -- bash -lc "bash '$path'; echo; read -r -p 'Nhan Enter de dong...' _"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -T "Thêm Cấu hình" -e bash -lc "bash '$path'; echo; read -r -p 'Nhan Enter...' _"
  else
    bash "$path"
  fi
}

pick_zenity() {
  zenity --list --title="JustPlay Công cụ IT (Ubuntu)" \
    --text="Chọn công cụ cài trên Ubuntu (.deb / script)" \
    --column="Mã" --column="Công cụ" --hide-column=1 --print-column=1 \
    --width=420 --height=280 \
    rustdesk "Cài RustDesk" \
    equipment "Thêm Cấu hình" \
    raidrive "Cài RaiDrive" \
    quit "Thoát"
}

pick_tty() {
  echo '========================================'
  echo ' JustPlay Công cụ IT (Ubuntu)'
  echo '========================================'
  echo ' 1) Cài RustDesk'
  echo ' 2) Thêm Cấu hình'
  echo ' 3) Cài RaiDrive'
  echo ' 0) Thoát'
  read -r -p 'Chọn: ' n
  case "$n" in
    1) echo rustdesk ;;
    2) echo equipment ;;
    3) echo raidrive ;;
    *) echo quit ;;
  esac
}

while true; do
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    choice="$(pick_zenity || true)"
  else
    choice="$(pick_tty)"
  fi
  case "${choice:-quit}" in
    rustdesk) run_script "$RD" "Cài RustDesk" ;;
    equipment) run_equipment "$EQ" ;;
    raidrive) run_script "$RAI" "Cài RaiDrive" ;;
    quit|"") exit 0 ;;
    *) ;;
  esac
done
