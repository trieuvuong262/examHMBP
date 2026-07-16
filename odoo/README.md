# Odoo Community — Phase 0 (JustPlay)

Stack Docker **tách hoàn toàn** khỏi Portal (`/opt/portaljustplay`).

| | Portal | Odoo |
|--|--------|------|
| Thư mục | `/opt/portaljustplay` | `/opt/odoo` |
| Domain | `portal.justplay.vn` | `erp.justplay.vn` |
| Database | PostgreSQL Portal | PostgreSQL riêng (container `odoo-db`) |
| Đăng nhập | Django User | Odoo User (tách biệt Phase 0) |

## Triển khai nhanh (VPS)

```bash
# Từ máy dev (PowerShell) — copy stack lên VPS
scp -r odoo root@103.90.224.203:/opt/

# Trên VPS
cd /opt/odoo
cp .env.example .env
nano .env   # đặt ODOO_DB_PASSWORD, ODOO_ADMIN_PASSWORD
chmod +x deploy.sh scripts/*.sh
./deploy.sh

# Cập nhật nginx Portal (git pull hoặc copy erp*.conf) rồi:
cd /opt/portaljustplay
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d nginx

# SSL erp.justplay.vn
cd /opt/odoo && ./scripts/setup-ssl-erp.sh
```

## Sau khi mở https://erp.justplay.vn/

1. Màn hình **Create database**:
   - Master password = `ODOO_ADMIN_PASSWORD` trong `/opt/odoo/.env`
   - Database name: `justplay_pilot`
   - Language: Vietnamese
   - Country: Vietnam
2. Cài module pilot (Apps):
   - **Inventory** (Kho)
   - **Manufacturing** (Sản xuất / MRP)
   - **Purchase** (Mua hàng)
   - **Sales** (Bán hàng) — tùy chọn
3. Bật **Product Variants** (màu, size) trong Settings → Inventory

## Bảo mật Phase 0

- Odoo chỉ listen `127.0.0.1:8069` — truy cập qua nginx HTTPS.
- Sau khi tạo DB xong, trong `config/odoo.conf` đặt `list_db = False` và `./deploy.sh` lại.
- Lưu `/opt/odoo/.env` — không commit.

## Tài nguyên VPS (~8 GB RAM)

Giới hạn container: Odoo 2 GB, Postgres Odoo 1 GB. Theo dõi `free -h` khi pilot.

## Phase tiếp theo

- App hub SX: **`justplay_sx`** (menu *Sản xuất JustPlay*) — xem [`docs/odoo18/sx-hub-scaffold.md`](../docs/odoo18/sx-hub-scaffold.md)
- Menu link từ Portal sidebar → `https://erp.justplay.vn`
- Đồng bộ nhân viên Portal → Odoo (`hr.employee`)
- SSO (Keycloak) — khi >30 user dùng hàng ngày
- Bridge thành phẩm / đơn KiotViet → Odoo (sau scaffold)
