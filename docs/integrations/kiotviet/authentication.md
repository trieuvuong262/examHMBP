# Xác thực — KiotViet Public API

## Cơ chế

- **OAuth 2.0**
- Cần `ClientId` và `client_secret` — lấy trên UI: **Thiết lập → Cửa hàng → Kết nối API** ([huong-dan-ket-noi-api.md](./huong-dan-ket-noi-api.md))
- Thư viện tham khảo (tài liệu gốc): OAuth2Client (.NET), oauth2-client (PHP)

## Endpoints OAuth

| | URL |
|---|-----|
| Authorization | `https://id.kiotviet.vn/connect/authorize` |
| Token | `POST https://id.kiotviet.vn/connect/token` |

## 2.2 Lấy Access Token

**POST** `https://id.kiotviet.vn/connect/token`

**Header:** `Content-Type: application/x-www-form-urlencoded`

**Body (form):**

| Tham số | Giá trị |
|---------|---------|
| scope | `PublicApi.Access` |
| grant_type | `client_credentials` |
| client_id | Client Id từ KiotViet |
| client_secret | Mã bảo mật |

**Response mẫu:**

```json
{
  "access_token": "",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

`expires_in`: 86400 giây (24h) — cần refresh/lấy token mới trước khi hết hạn.

## Header mọi API Public (trừ token)

```http
Retailer: taphoa
Authorization: Bearer eyJhbGciOiJSU0EtT0FFUCIs...
```

- `Retailer`: **tên cửa hàng** (slug/identifier trên KiotViet), không phải tên hiển thị.

## Partner header (một số luồng đặt hàng)

Khi tạo đơn từ MyKiot / KV Sync, thêm header `Partner`:

| Nguồn | Giá trị |
|-------|---------|
| MyKiot | `MyKiot` |
| KV Sync | `KVSync` |
