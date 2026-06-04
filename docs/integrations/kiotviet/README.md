# KiotViet Public API — tài liệu tham chiếu (local)

Tài liệu lưu nội bộ để triển khai tích hợp sau.

**Nguồn:**

1. **Public API Ver 4.0** (PDF/paste) — Công ty CP Phần mềm Citigo  
2. **Hướng dẫn portal KiotViet Retail** — [Kết nối API](https://www.kiotviet.vn/huong-dan-su-dung-kiotviet/retail-ket-noi-api/ket-noi-api/#3-tong-quan-ve-public-api-4-2)

## Liên hệ / hỗ trợ (theo tài liệu gốc)

| | |
|---|---|
| Công ty | Công ty CP Phần mềm Citigo |
| Sản phẩm | [KiotViet](https://www.kiotviet.vn) |
| Email bán hàng | sale@citigo.net |
| Email hỗ trợ API | support@kiotviet.com |
| Hà Nội | Số 1B Yết Kiêu, Hoàn Kiếm — Tel/Fax: 04 628 00 488 / 04 628 00 191 |
| TP.HCM | Lầu 6, Tòa WASECO, 10 Phổ Quang, Tân Bình |

## Endpoint chính

| Mục đích | URL |
|----------|-----|
| OAuth token | `POST https://id.kiotviet.vn/connect/token` |
| OAuth authorize | `https://id.kiotviet.vn/connect/authorize` |
| Public API | `https://public.kiotapi.com/` |

## Cấu trúc thư mục

| File | Nội dung |
|------|----------|
| [TOC.md](./TOC.md) | Mục lục đầy đủ (Ver 4.0) |
| [overview.md](./overview.md) | Giới thiệu, phạm vi API |
| [authentication.md](./authentication.md) | OAuth 2.0, lấy access token, header request |
| [endpoints-index.md](./endpoints-index.md) | Danh sách API theo module (method + path) |
| [settings-and-limits.md](./settings-and-limits.md) | Thiết lập cửa hàng, giới hạn GET, ghi chú tích hợp |
| [revision-history.md](./revision-history.md) | Lịch sử phiên bản tài liệu (tóm tắt) |
| [huong-dan-ket-noi-api.md](./huong-dan-ket-noi-api.md) | Thiết lập trên UI Retail, OTP, bật/tắt API |
| [connection-justsport.md](./connection-justsport.md) | Metadata kết nối gian hàng JustSport (không secret) |
| [_source-portal-ket-noi-api-raw.md](./_source-portal-ket-noi-api-raw.md) | Bản scrape thô trang portal (có menu/footer) |
| [_source-paste-raw.txt](./_source-paste-raw.txt) | Toàn bộ nội dung paste gốc (TOC + revision + API) |
| [api-reference-full.txt](./api-reference-full.txt) | Phần mô tả API chi tiết (từ mục 1–2 trở đi) |

## Header bắt buộc (mọi API trừ token)

```http
Retailer: {ten_cua_hang}
Authorization: Bearer {access_token}
```

## Credentials

Lấy trong KiotViet Retail (admin): **Thiết lập** → **Cửa hàng** → **Kết nối API** → OTP SĐT hợp đồng → **Tạo mã** → `Client ID` + **Mã bảo mật** (`client_secret`).  
Chi tiết từng bước: [huong-dan-ket-noi-api.md](./huong-dan-ket-noi-api.md).  
Nếu không có quyền: liên hệ CSKH KiotViet (1900 6522).

Scope token: `PublicApi.Access`  
Grant type: `client_credentials`

## Gian hàng đã cấu hình

| | |
|---|---|
| Kết nối | **justsport** — Đang hoạt động |
| Quyền API | Khách hàng, hóa đơn, đơn đặt hàng |
| Metadata | [connection-justsport.md](./connection-justsport.md) |
| Credentials | `.env` — `KIOTVIET_*` (không commit) |

## Trạng thái trong Portal Just Play

- Chưa có code gọi API KiotViet; biến môi trường đã chuẩn bị.
- Khi bắt đầu: đọc `authentication.md` → `endpoints-index.md` → module cần (thường `products`, `orders`, `invoices`).

## File gốc ngoài repo

Nên giữ bản PDF/Word chính thức từ Citigo (157 trang) cùng thư mục này hoặc trong kho tài liệu công ty để tra cứu request/response chi tiết.
