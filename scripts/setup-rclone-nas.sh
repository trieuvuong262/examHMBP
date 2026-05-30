#!/bin/bash
set -euo pipefail

apt-get update -qq
apt-get install -y -qq rclone fuse3

NAS_USER=$(grep '^username=' /root/.nas-cred | cut -d= -f2-)
NAS_PASS=$(grep '^password=' /root/.nas-cred | cut -d= -f2-)
OBSCURED=$(rclone obscure "$NAS_PASS")

rclone config delete synology 2>/dev/null || true
rclone config create synology smb host 100.93.5.42 user "$NAS_USER" pass "$OBSCURED"

echo "=== rclone lsd ==="
rclone lsd synology:DATACHUNG

fusermount -u /mnt/nas-portal 2>/dev/null || true
mkdir -p /mnt/nas-portal
rclone mount synology:DATACHUNG /mnt/nas-portal \
  --daemon --allow-other --vfs-cache-mode writes --dir-cache-time 72h --poll-interval 1m

sleep 2
echo "=== ls /mnt/nas-portal ==="
ls -la /mnt/nas-portal

cat > /etc/systemd/system/rclone-nas.service << 'UNIT'
[Unit]
Description=Rclone mount NAS DATACHUNG
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/rclone mount synology:DATACHUNG /mnt/nas-portal --allow-other --vfs-cache-mode writes --dir-cache-time 72h --poll-interval 1m
ExecStop=/bin/fusermount -u /mnt/nas-portal
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable rclone-nas.service
echo "=== done ==="
