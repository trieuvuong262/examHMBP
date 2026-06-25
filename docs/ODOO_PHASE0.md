# Odoo Phase 0 — JustPlay

Đã triển khai **Odoo 18 Community** tách khỏi Portal trên VPS `103.90.224.203`.

## Truy cập

| | |
|--|--|
| URL | https://erp.justplay.vn/ |
| Stack | `/opt/odoo` |
| Nginx/SSL | Proxy qua Portal nginx (`justplay_edge` Docker network) |

## Mật khẩu (trên VPS)

```bash
ssh root@103.90.224.203
grep ODOO_ADMIN_PASSWORD /opt/odoo/.env   # Master password — màn hình tạo database
grep ODOO_DB_PASSWORD /opt/odoo/.env      # PostgreSQL Odoo (nội bộ)
```

**Không commit** file `/opt/odoo/.env`.

## Tạo database pilot (lần đầu)

1. Mở https://erp.justplay.vn/
2. **Master Password** = `ODOO_ADMIN_PASSWORD` trong `.env`
3. Database name: `justplay_pilot`
4. Language: Vietnamese · Country: Vietnam
5. Apps: **Inventory**, **Manufacturing**, **Purchase** (+ Sales nếu cần)

Sau khi tạo DB, trong `/opt/odoo/config/odoo.conf` đặt `list_db = False` rồi `cd /opt/odoo && ./deploy.sh`.

## Cập nhật / khởi động lại

```bash
cd /opt/odoo && ./deploy.sh
cd /opt/portaljustplay && docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d nginx
```

## Cấu trúc repo

- `odoo/` — docker-compose, config, scripts
- `PortalJustPlay/nginx/erp*.conf` — reverse proxy
- `docker-compose.yml` — nginx thêm network `justplay_edge`

Xem thêm: [odoo/README.md](../odoo/README.md)
