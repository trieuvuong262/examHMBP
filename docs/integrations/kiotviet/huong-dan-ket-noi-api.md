# Kết nối API — Hướng dẫn KiotViet Retail (portal)

Nguồn: [Kết nối API — KiotViet Retail](https://www.kiotviet.vn/huong-dan-su-dung-kiotviet/retail-ket-noi-api/ket-noi-api/)  
Anchor mục Public API: [#3-tong-quan-ve-public-api-4-2](https://www.kiotviet.vn/huong-dan-su-dung-kiotviet/retail-ket-noi-api/ket-noi-api/#3-tong-quan-ve-public-api-4-2)

**Phạm vi:** Ngành **Bán buôn, Bán lẻ** (KiotViet Retail).  
**Lưu trong repo:** tháng 5/2026 — dùng cùng tài liệu Public API Ver 4.0 trong thư mục này.

---

## I. Giới thiệu chung

Tính năng **Kết nối API** (Application Programming Interface) cho phép gian hàng chủ động tích hợp dữ liệu với hệ thống bên ngoài (website, sàn TMĐT, CRM) một cách linh hoạt và bảo mật.

### Lợi ích (theo KiotViet)

| | Mô tả |
|---|--------|
| **Tích hợp hệ thống mở rộng** | Mở cổng API để liên kết đối tác thứ 3: website, TMĐT, CRM. |
| **Quản lý dữ liệu toàn diện** | Đọc/ghi: Nhóm hàng, Hàng hóa, Đặt hàng, Hóa đơn, Khách hàng, Phiếu nhập hàng — đồng bộ với nền tảng khác. |
| **Bảo mật** | Mã API chỉ hiển thị với **admin chủ gian hàng**; admin kiểm soát quyền truy xuất dữ liệu nhạy cảm. |

---

## II. Thao tác cơ bản

### 1. Thiết lập kết nối và lấy thông tin API

**Tình huống:** Quản trị viên cần **Client ID** và **Mã bảo mật** (`client_secret`) cho đội kỹ thuật tích hợp.

**Các bước trên giao diện KiotViet:**

1. Màn hình **Quản lý** → **Thiết lập** → **Cửa hàng**.
2. Menu trái: **Kết nối API** → **Chỉnh sửa**.
3. Nhập **số điện thoại trên hợp đồng** → **Nhận mã xác thực**.
4. Nhập mã OTP gửi về SĐT → **Tiếp tục**.
5. Mục **Mã bảo mật** → **Tạo mã**.
6. Đọc điều khoản, tích đồng ý → **Đồng ý**.
7. Tích: **Cho phép truy xuất thông tin khách hàng, hoá đơn, đặt hàng từ gian hàng của bạn** → **Lưu**.
8. Cung cấp **Client ID** và **Mã bảo mật** cho bên thứ 3 (hoặc lưu vào biến môi trường server — không commit vào git).

**Map sang tích hợp kỹ thuật:** xem [authentication.md](./authentication.md) (OAuth `client_credentials`, scope `PublicApi.Access`).

> Trên tài liệu PDF Citigo cũ có thể ghi “Thiết lập kết nối API” trong **Thiết lập cửa hàng** — cùng mục đích; UI Retail hiện tại: **Thiết lập → Cửa hàng → Kết nối API**.

---

### 2. Ngừng hoạt động kết nối API

**Tình huống:** Tạm ngắt kết nối hệ thống bên thứ ba, vô hiệu hóa API để an toàn dữ liệu.

1. Vào **Thông tin kết nối API** (cùng đường dẫn mục 1).
2. **Chỉnh sửa** → trạng thái **Ngừng hoạt động**.
3. **Lưu**.

Token đã cấp trước đó sẽ không còn hiệu lực sau khi ngắt (cần bật lại và có thể phải tạo lại mã bảo mật tùy chính sách gian hàng).

---

### 3. Tổng quan về Public API

**Giới thiệu:** Public API hỗ trợ tích hợp và trao đổi dữ liệu giữa KiotViet và website / TMĐT / CRM.

**Đối tượng hỗ trợ (đọc & ghi):**

| Đối tượng | Thao tác |
|-----------|----------|
| Nhóm hàng | Danh sách, tên nhóm, quan hệ cha–con |
| Hàng hóa | CRUD sản phẩm, thuộc tính |
| Đặt hàng | Lấy / tạo / cập nhật / hủy đơn |
| Hóa đơn | Lấy / tạo / cập nhật / hủy |
| Khách hàng | Danh sách và thao tác KH |
| Phiếu nhập hàng | Thông tin phiếu nhập |

**Chi tiết kỹ thuật (request/response, endpoint):** không nằm trên trang portal này — dùng:

- [api-reference-full.txt](./api-reference-full.txt) hoặc [_source-paste-raw.txt](./_source-paste-raw.txt) — bản Citigo Public API **Ver 4.0**
- [endpoints-index.md](./endpoints-index.md) — chỉ mục URL
- [TOC.md](./TOC.md) — mục lục đầy đủ

**Base URL API:** `https://public.kiotapi.com/`  
**OAuth token:** `POST https://id.kiotviet.vn/connect/token`

---

## Liên hệ hỗ trợ (trang KiotViet)

| Kênh | Số / email |
|------|------------|
| Tư vấn bán hàng | 1800 6162 |
| Chăm sóc khách hàng | 1900 6522 |
| Email | hotro@kiotviet.com |

---

## Tài liệu liên quan trong repo

| File | Nội dung |
|------|----------|
| [README.md](./README.md) | Tổng quan tích hợp + cấu trúc thư mục |
| [authentication.md](./authentication.md) | Header, OAuth, token |
| [settings-and-limits.md](./settings-and-limits.md) | GET 5000/h, phân trang, `settings` |
