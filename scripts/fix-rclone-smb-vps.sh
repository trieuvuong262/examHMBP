#!/bin/bash
# Sửa rclone SMB trên VPS + NAS (Synology Directory Server).
# Chạy trên VPS: bash scripts/fix-rclone-smb-vps.sh
set -euo pipefail

CRED_FILE="${CRED_FILE:-/root/.nas-cred}"
RCLONE_BIN="${RCLONE_BIN:-/usr/local/bin/rclone}"
NAS_HOST="${NAS_HOST:-100.93.5.42}"
REMOTE_NAME="${REMOTE_NAME:-synology}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/nas-portal}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/portaljustplay/docker-compose.yml}"

if [[ ! -f "$CRED_FILE" ]]; then
  echo "ERROR: missing $CRED_FILE"
  exit 1
fi

NAS_USER=$(grep '^username=' "$CRED_FILE" | cut -d= -f2-)
NAS_PASS=$(grep '^password=' "$CRED_FILE" | cut -d= -f2-)
if [[ -z "$NAS_USER" || -z "$NAS_PASS" ]]; then
  echo "ERROR: username/password empty in $CRED_FILE"
  exit 1
fi

install_rclone() {
  if [[ -x "$RCLONE_BIN" ]] && "$RCLONE_BIN" version | grep -q 'v1.7'; then
    echo "==> rclone OK: $($RCLONE_BIN version | head -1)"
    return 0
  fi
  echo "==> Install rclone latest to $RCLONE_BIN"
  apt-get update -qq
  apt-get install -y -qq unzip curl
  tmpdir=$(mktemp -d)
  curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o "$tmpdir/rclone.zip"
  unzip -o -q "$tmpdir/rclone.zip" -d "$tmpdir"
  install -m 755 "$tmpdir"/rclone-*-linux-amd64/rclone "$RCLONE_BIN"
  rm -rf "$tmpdir"
  "$RCLONE_BIN" version | head -1
}

fix_nas_cifs_mode() {
  echo "==> NAS: đặt LDAP CIFS support = ldapsam (local + LDAP SMB)"
  docker compose -f "$COMPOSE_FILE" exec -T web python manage.py shell <<'PY'
from nas_storage.nas_acl_apply import _run_ssh_commands

out = _run_ssh_commands([
    '/usr/syno/bin/synoldapclient --status 2>&1 | grep CIFS',
    '/usr/syno/bin/synoldapclient --support-cifs ldapsam 2>&1',
    '/usr/syno/bin/synoldapclient --status 2>&1 | grep CIFS',
])
print(out)
PY
}

recreate_rclone_remote() {
  echo "==> Recreate rclone remote [$REMOTE_NAME]"
  OBSCURED=$("$RCLONE_BIN" obscure "$NAS_PASS")
  "$RCLONE_BIN" config delete "$REMOTE_NAME" 2>/dev/null || true
  "$RCLONE_BIN" config create "$REMOTE_NAME" smb host "$NAS_HOST" user "$NAS_USER" pass "$OBSCURED"
  "$RCLONE_BIN" config show "$REMOTE_NAME"
  "$RCLONE_BIN" lsd "${REMOTE_NAME}:" | head -8
}

remount_nas() {
  echo "==> Remount $MOUNT_POINT"
  cat > /etc/systemd/system/rclone-nas.service <<UNIT
[Unit]
Description=Rclone mount NAS (tailscale-justplay)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=${RCLONE_BIN} mount ${REMOTE_NAME}: ${MOUNT_POINT} \\
  --allow-other --vfs-cache-mode writes \\
  --dir-cache-time 5s --poll-interval 5s --attr-timeout 1s
ExecStop=/bin/fusermount -u ${MOUNT_POINT}
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable rclone-nas.service
  systemctl stop rclone-nas.service 2>/dev/null || true
  fusermount -u "$MOUNT_POINT" 2>/dev/null || true
  sleep 1
  mkdir -p "$MOUNT_POINT"
  systemctl start rclone-nas.service
  sleep 3
  ls -la "$MOUNT_POINT" | head -10
}

test_container() {
  echo "==> Container rclone"
  docker compose -f "$COMPOSE_FILE" exec -T web rclone lsd synology: 2>&1 | head -8
}

install_rclone
fix_nas_cifs_mode
recreate_rclone_remote
remount_nas
test_container
echo "==> done"
