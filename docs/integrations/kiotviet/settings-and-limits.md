# Thiết lập cửa hàng & giới hạn — KiotViet API

## Giới hạn request

- **GET:** tối đa **5000 request/giờ** (ghi trong tài liệu Ver 3.8+).

## Phân trang (thường gặp)

| Tham số | Mô tả |
|---------|--------|
| `pageSize` | Mặc định 20, tối đa **100** / trang |
| `currentItem` | Offset / bản ghi bắt đầu (mặc định 0) |
| `orderBy` | Trường sắp xếp |
| `orderDirection` | `Asc` (mặc định) hoặc `Desc` |
| `lastModifiedFrom` | Lọc/sync theo thời gian cập nhật |

## GET settings cửa hàng

**GET** `https://public.kiotapi.com/settings`

Response ví dụ (một phần):

| Field | Ý nghĩa |
|-------|---------|
| `ManagerCustomerByBranch` | Quản lý KH theo chi nhánh |
| `AllowOrderWhenOutStock` | Cho phép đặt hàng khi hết tồn |
| `AllowSellWhenOrderOutStock` | Bán / chuyển hàng khi SP đã được đặt hàng |

Nhiều API đặt hàng/hóa đơn **trả lỗi** nếu thiết lập tương ứng trên KiotViet **chưa bật** (ví dụ: Cho phép đặt hàng, Sử dụng giao hàng, Không đổi thời gian bán hàng, v.v.).

## Webhook

- Đăng ký: `POST https://public.kiotapi.com/webhooks`
- Hủy: `DELETE https://public.kiotapi.com/webhooks/{id}`
- Push events: customer, product, stock, order, invoice, pricebook, category, branch, ...

Chi tiết payload: mục 2.11 trong tài liệu gốc / PDF.
