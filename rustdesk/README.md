# RustDesk self-host — JustPlay

Stack Docker **tách hoàn toàn** khỏi Portal (`/opt/portaljustplay`).

| | Portal | RustDesk |
|--|--------|----------|
| Thư mục | `/opt/portaljustplay` | `/opt/rustdesk` |
| Compose | `docker-compose.yml` | `rustdesk/docker-compose.yml` |
| Port | 80, 443, 5432 (local) | 21115–21117 TCP, 21116 UDP |
| Deploy | `./deploy.sh` | `rustdesk/deploy.sh` |

Tài liệu đầy đủ: [docs/RUSTDESK_SELF_HOST.md](../docs/RUSTDESK_SELF_HOST.md)

## Triển khai nhanh (VPS)

```bash
sudo mkdir -p /opt/rustdesk
# Copy thư mục rustdesk/ lên VPS (rsync/scp/git)
cd /opt/rustdesk
cp .env.example .env
nano .env   # RUSTDESK_PUBLIC_HOST=rd.justplay.vn
chmod +x deploy.sh scripts/*.sh
./deploy.sh
```

Sau deploy, lấy public key:

```bash
cat /opt/rustdesk/data/id_ed25519.pub
```

## DNS (khuyến nghị)

Tạo bản ghi **A** `rd.justplay.vn` → `103.90.224.203` (RustDesk).

## Client Windows (IT)

```powershell
.\scripts\rustdesk-configure-client-windows.ps1 `
  -ServerHost rd.justplay.vn `
  -PublicKey "NỘI_DUNG_id_ed25519.pub"
```

## Bảo mật

- Bắt buộc **ghim public key** trên mọi client.
- Mật khẩu unattended mạnh, chỉ IT được biết.
- `ALWAYS_USE_RELAY=Y` — traffic qua relay VPS (dễ kiểm soát).
- Backup `data/id_ed25519` và `id_ed25519.pub` — mất key phải cấu hình lại toàn bộ client.
