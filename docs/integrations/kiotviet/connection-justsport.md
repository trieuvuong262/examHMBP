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

## Bảo mật

- Đã chia sẻ secret trong chat/ảnh → nên **tạo lại Mã bảo mật** trên KiotViet nếu repo hoặc kênh chat không riêng tư.
- VPS: thêm các biến trên vào `.env` trên server (không đẩy lên Git).
