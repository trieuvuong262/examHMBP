# 1. Giới thiệu — KiotViet Public API

Nguồn: Tài liệu hướng dẫn sử dụng Public API **Ver 4.0**, Citigo.

## Mục đích

KiotViet Public API hỗ trợ **tích hợp và trao đổi dữ liệu** giữa KiotViet và:

- Website / thương mại điện tử
- CRM
- Hệ thống nội bộ / ERP

## Đối tượng API hỗ trợ (đọc / ghi)

| Module | Mô tả ngắn |
|--------|------------|
| Nhóm hàng (`categories`) | Danh mục, quan hệ cha–con (tối đa 3 cấp) |
| Hàng hóa (`products`) | SP, thuộc tính, tồn kho, bảng giá, IMEI/lô date, BOM/combo |
| Đặt hàng (`orders`) | Đơn đặt hàng — tạo / cập nhật / hủy |
| Hóa đơn (`invoices`) | Hóa đơn bán — tạo / cập nhật / hủy |
| Khách hàng (`customers`) | Danh sách & thao tác KH |
| Phiếu nhập (`purchaseorders`) | Nhập hàng NCC |
| API phụ trợ | Chi nhánh, user, TK ngân hàng, thu khác, webhook, nhóm KH, sổ quỹ |

## Ghi chú chung

- Tham số có `?` trong tài liệu gốc = **không bắt buộc**.
- Chi tiết từng field request/response: xem bản PDF đầy đủ hoặc tra cứu khi implement từng endpoint.
