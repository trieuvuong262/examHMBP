#!/bin/sh
# Nâng trần quét INSTREAM trước khi /init khởi động clamd.
# Image clamav/clamav mặc định StreamMaxLength/MaxFileSize ~100M — thấp hơn
# AV_SCAN_MAX_BYTES=200M của portal thì clamd từ chối giữa chừng.
set -eu

CONF="${CLAMD_CONF_PATH:-/etc/clamav/clamd.conf}"
STREAM_MAX="${CLAM_STREAM_MAX_LENGTH:-200M}"
FILE_MAX="${CLAM_MAX_FILE_SIZE:-200M}"
SCAN_MAX="${CLAM_MAX_SCAN_SIZE:-400M}"

set_opt() {
    key="$1"
    val="$2"
    if [ ! -f "$CONF" ]; then
        return 0
    fi
    if grep -qE "^[[:space:]]*#?[[:space:]]*${key}([[:space:]]|$)" "$CONF"; then
        sed -i -E "s|^[[:space:]]*#?[[:space:]]*${key}([[:space:]].*)?$|${key} ${val}|" "$CONF"
    else
        printf '%s %s\n' "$key" "$val" >> "$CONF"
    fi
}

if [ -f "$CONF" ]; then
    set_opt StreamMaxLength "$STREAM_MAX"
    set_opt MaxFileSize "$FILE_MAX"
    set_opt MaxScanSize "$SCAN_MAX"
fi

exec /init "$@"
