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

## Bảo mật

- Đã chia sẻ secret trong chat/ảnh → nên **tạo lại Mã bảo mật** trên KiotViet nếu repo hoặc kênh chat không riêng tư.
- VPS: thêm các biến trên vào `.env` trên server (không đẩy lên Git).
