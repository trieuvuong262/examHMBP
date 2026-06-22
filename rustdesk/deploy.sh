#!/usr/bin/env bash
set -Eeuo pipefail

# Triển khai RustDesk OSS — KHÔNG đụng Portal (/opt/portaljustplay).
#
# Trên VPS (lần đầu):
#   sudo mkdir -p /opt/rustdesk
#   sudo rsync -a rustdesk/ /opt/rustdesk/   # hoặc git clone / copy thủ công
#   cd /opt/rustdesk && cp .env.example .env && nano .env
#   chmod +x deploy.sh scripts/*.sh
#   ./deploy.sh
#
# Cập nhật:
#   cd /opt/rustdesk && ./deploy.sh

RUSTDESK_DIR="${RUSTDESK_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$RUSTDESK_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: Thiếu $RUSTDESK_DIR/.env — chạy: cp .env.example .env && chỉnh RUSTDESK_PUBLIC_HOST"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ -z "${RUSTDESK_PUBLIC_HOST:-}" ]]; then
  echo "ERROR: RUSTDESK_PUBLIC_HOST trống trong .env"
  exit 1
fi

compose() {
  docker compose "$@"
}

echo "==> RustDesk self-host (tách khỏi Portal)"
echo "    Thư mục: $RUSTDESK_DIR"
echo "    Host:    $RUSTDESK_PUBLIC_HOST"
echo "    Image:   ${RUSTDESK_IMAGE:-rustdesk/rustdesk-server:1.1.14}"

mkdir -p data
chmod 700 data

# Trên VPS: đảm bảo hbbs resolve được domain trước khi DNS public propagate
if [[ -n "${RUSTDESK_PUBLIC_HOST:-}" && -n "${RUSTDESK_VPS_IP:-}" ]]; then
  if [[ ! "$RUSTDESK_PUBLIC_HOST" =~ ^[0-9.]+$ ]]; then
    if ! getent hosts "$RUSTDESK_PUBLIC_HOST" >/dev/null 2>&1; then
      if ! grep -qF "$RUSTDESK_PUBLIC_HOST" /etc/hosts 2>/dev/null; then
        echo "==> Thêm /etc/hosts: ${RUSTDESK_VPS_IP} ${RUSTDESK_PUBLIC_HOST}"
        echo "${RUSTDESK_VPS_IP} ${RUSTDESK_PUBLIC_HOST}" >> /etc/hosts
      fi
    fi
  fi
fi

echo "==> Pull image..."
compose pull

echo "==> Khởi động hbbr + hbbs..."
compose up -d

echo "==> Trạng thái container:"
compose ps

if [[ -x "$RUSTDESK_DIR/scripts/rustdesk-ufw.sh" ]]; then
  echo "==> Firewall (chỉ port RustDesk)..."
  bash "$RUSTDESK_DIR/scripts/rustdesk-ufw.sh"
fi

echo ""
echo "==> Public key (client phải ghim key này):"
if [[ -f data/id_ed25519.pub ]]; then
  cat data/id_ed25519.pub
  chmod 600 data/id_ed25519 data/id_ed25519.pub 2>/dev/null || true
else
  echo "    Chưa có data/id_ed25519.pub — đợi vài giây rồi chạy: cat data/id_ed25519.pub"
fi

echo ""
echo "==> Kiểm tra nhanh:"
echo "    docker logs rustdesk-hbbs --tail 20"
echo "    docker logs rustdesk-hbbr --tail 20"
echo ""
echo "Xong. Cấu hình client: docs/RUSTDESK_SELF_HOST.md"
