# Kết nối API — gian hàng JustSport (metadata)

> **Không lưu Client Secret trong file này.** Giá trị thật nằm trong `.env` / `.env.local` (đã gitignore).

| Trường | Giá trị |
|--------|---------|
| Tên kết nối | `justsport` |
| Trạng thái | Đang hoạt động |
| Quyền bên thứ 3 | Khách hàng, hóa đơn, đơn đặt hàng |
| Header `Retailer` (dự kiến) | `justsport` — khớp tên kết nối / subdomain gian hàng |

**Client ID & Mã bảo mật:** chỉ trong `.env` / `.env.local` (gitignore), không ghi trong repo.

## Biến môi trường (Portal)

Xem mẫu trong `.env.example` (`KIOTVIET_*`). Máy dev: đã ghi vào `.env` local (nếu chưa có block KIOTVIET).

## OAuth / API

- Token: `POST https://id.kiotviet.vn/connect/token`
- API: `https://public.kiotapi.com/`
- Scope: `PublicApi.Access`

Xem [authentication.md](./authentication.md).

## Menu không hiện trên VPS?

Menu **KiotViet** chỉ hiện khi **cả hai** điều kiện sau đúng trên server:

1. **Code đã deploy** (có app `kiotviet` + sidebar mới) — `git pull` + `./deploy.sh`
2. **File `.env` trên VPS** (không commit từ máy dev) có:

```env
KIOTVIET_ENABLED=1
KIOTVIET_RETAILER=justsport
KIOTVIET_CLIENT_ID=fbbc5d8c-14b2-41b2-9ba5-479b3237a2d6
KIOTVIET_CLIENT_SECRET=<mã bảo mật>
```

Sau khi sửa `.env` tại `/opt/portaljustplay/.env`:

```bash
# restart KHÔNG nạp lại biến mới — phải recreate:
docker compose up -d web --force-recreate
```

Kiểm tra trong container:

```bash
docker compose exec web python manage.py kiotviet_status
```

Nếu `kiotviet_is_live() = False` → thiếu biến môi trường.  
Menu chỉ hiện khi API đã cấu hình **và** user được cấp module **kiotviet** (phòng ban / nhóm quyền). **Superuser** hoặc username **`admin`** bypass; `is_staff` **không** tự mở menu.  
Nhân viên khác cần bật module **KiotViet** trong **Phân quyền** → phòng ban.

## Database trung gian (mirror `kv_*`)

Portal lưu bản sao dữ liệu KiotViet trên **PostgreSQL hiện có** (cùng container `db`), bảng prefix `kv_*`. Menu tra cứu **chỉ đọc mirror** (`KIOTVIET_USE_LOCAL_MIRROR=1`); không gọi API trực tiếp từ giao diện.

### Triển khai lần đầu trên VPS

```bash
cd /opt/portaljustplay
git pull
docker compose up -d web --force-recreate
docker compose exec web python manage.py migrate
docker compose exec web python manage.py kiotviet_sync --full
docker compose exec web python manage.py kiotviet_status
```

### Đồng bộ định kỳ (cron)

Cấu hình lịch và entity trong **Quản Trị Hệ thống → Đồng bộ KiotViet** (5p / 30p / 6h / 12h / 24h). Trên VPS:

```bash
sudo bash scripts/setup-kiotviet-cron.sh 1440   # ví dụ: mỗi 24h
```

Cron chạy `kiotviet_sync` **incremental** (chỉ bản ghi mới/thay đổi). Log: `/var/log/portal-kiotviet-sync.log`.

### Biến môi trường thêm (tùy chọn)

```env
KIOTVIET_USE_LOCAL_MIRROR=1
KIOTVIET_SYNC_PAGE_SIZE=100
KIOTVIET_API_TIMEOUT=90
KIOTVIET_API_TIMEOUT_ORDERS=180
```

Lệnh hữu ích:

```bash
python manage.py kiotviet_sync --entity products --entity customers
python manage.py kiotviet_sync --entity purchase_orders
python manage.py kiotviet_sync --refresh-images
```

Chi tiết schema: [schema-design.md](./schema-design.md).

## Bảo mật

- Đã chia sẻ secret trong chat/ảnh → nên **tạo lại Mã bảo mật** trên KiotViet nếu repo hoặc kênh chat không riêng tư.
- VPS: thêm các biến trên vào `.env` trên server (không đẩy lên Git).
