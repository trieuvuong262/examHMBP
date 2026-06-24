#!/bin/sh
# Khởi động WoL Relay trên NAS (Synology / Linux)
# Đặt WOL_RELAY_SECRET trước khi chạy — trùng RUSTDESK_WOL_RELAY_SECRET trên Portal.

DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
export WOL_RELAY_SECRET="${WOL_RELAY_SECRET:-}"
export WOL_RELAY_BIND="${WOL_RELAY_BIND:-0.0.0.0}"
export WOL_RELAY_PORT="${WOL_RELAY_PORT:-39280}"
export WOL_RELAY_BROADCAST="${WOL_RELAY_BROADCAST:-}"

if [ -z "$WOL_RELAY_SECRET" ]; then
  echo "LOI: dat WOL_RELAY_SECRET (hoac sua file nay)" >&2
  exit 1
fi

exec python3 "$DIR/JustPlay-WoL-Relay.py"
