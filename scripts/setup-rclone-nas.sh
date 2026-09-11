#!/bin/bash
set -euo pipefail

# Cài rclone mới (SMB Synology cần >= 1.6x; Ubuntu repo thường quá cũ)
RCLONE_BIN="${RCLONE_BIN:-/usr/local/bin/rclone}"
if ! [[ -x "$RCLONE_BIN" ]] || ! "$RCLONE_BIN" version 2>/dev/null | grep -q 'v1.7'; then
  apt-get update -qq
  apt-get install -y -qq unzip curl
  tmpdir=$(mktemp -d)
  curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o "$tmpdir/rclone.zip"
  unzip -o -q "$tmpdir/rclone.zip" -d "$tmpdir"
  install -m 755 "$tmpdir"/rclone-*-linux-amd64/rclone "$RCLONE_BIN"
  rm -rf "$tmpdir"
fi

apt-get install -y -qq fuse3 2>/dev/null || apt-get install -y -qq rclone fuse3

NAS_USER=$(grep '^username=' /root/.nas-cred | cut -d= -f2-)
NAS_PASS=$(grep '^password=' /root/.nas-cred | cut -d= -f2-)
OBSCURED=$("$RCLONE_BIN" obscure "$NAS_PASS")

# Host SMB lấy từ NAS_SMB_HOST, nếu không có thì suy ra từ NAS_DSM_URL trong .env.
# Trước đây IP bị hardcode nên khi IP Tailscale của NAS đổi thì rclone trỏ vào
# địa chỉ chết và treo trọn --contimeout (1 phút) × retries ở mỗi lệnh.
ENV_FILE="${ENV_FILE:-/opt/portaljustplay/.env}"
NAS_SMB_HOST="${NAS_SMB_HOST:-}"
if [[ -z "$NAS_SMB_HOST" && -f "$ENV_FILE" ]]; then
  NAS_SMB_HOST=$(
    grep -E '^NAS_DSM_URL=' "$ENV_FILE" \
      | tail -1 | cut -d= -f2- | tr -d $'\r"'"'"' ' \
      | sed -E 's#^https?://##; s#[:/].*$##'
  )
fi
if [[ -z "$NAS_SMB_HOST" ]]; then
  echo "ERROR: khong xac dinh duoc host NAS." >&2
  echo "       Dat NAS_SMB_HOST=<ip-tailscale> hoac NAS_DSM_URL trong ${ENV_FILE}" >&2
  exit 1
fi
echo "=== NAS SMB host: ${NAS_SMB_HOST} ==="

# Kiem tra ket noi truoc khi cau hinh — that bai som thay vi treo o rclone
if ! timeout 10 bash -c "cat < /dev/null > /dev/tcp/${NAS_SMB_HOST}/445" 2>/dev/null; then
  echo "ERROR: khong mo duoc cong SMB 445 tren ${NAS_SMB_HOST} (10s)." >&2
  echo "       Kiem tra: tailscale status | grep ${NAS_SMB_HOST}" >&2
  echo "       IP Tailscale cua NAS co the da doi — cap nhat NAS_DSM_URL trong .env." >&2
  exit 1
fi
echo "    SMB 445 OK"

"$RCLONE_BIN" config delete synology 2>/dev/null || true
"$RCLONE_BIN" config create synology smb host "$NAS_SMB_HOST" user "$NAS_USER" pass "$OBSCURED"

echo "=== rclone lsd ==="
"$RCLONE_BIN" lsd synology: --contimeout 5s --timeout 10s --retries 1 --low-level-retries 2

fusermount -u /mnt/nas-portal 2>/dev/null || true
mkdir -p /mnt/nas-portal
# --daemon-timeout: kernel FUSE hủy request treo sau 15s (tránh kẹt D-state khi NAS mất mạng)
# --timeout/--contimeout: rclone lỗi nhanh thay vì treo vô hạn
"$RCLONE_BIN" mount synology: /mnt/nas-portal \
  --daemon --allow-other --vfs-cache-mode writes \
  --dir-cache-time 5s --poll-interval 5s --attr-timeout 1s \
  --daemon-timeout 15s --timeout 10s --contimeout 5s --retries 1 --low-level-retries 2

sleep 2
echo "=== ls /mnt/nas-portal ==="
ls -la /mnt/nas-portal

cat > /etc/systemd/system/rclone-nas.service << UNIT
[Unit]
Description=Rclone mount NAS (tailscale-justplay)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=${RCLONE_BIN} mount synology: /mnt/nas-portal \\
  --allow-other --vfs-cache-mode writes \\
  --dir-cache-time 5s --poll-interval 5s --attr-timeout 1s \\
  --daemon-timeout 15s --timeout 10s --contimeout 5s --retries 1 --low-level-retries 2
ExecStop=/bin/fusermount -u /mnt/nas-portal
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable rclone-nas.service
echo "=== done ==="
