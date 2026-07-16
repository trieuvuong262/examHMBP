# Hub Sản xuất trên Portal (SoT)

UX vận hành chính nằm trên **Portal** (`/san-xuat/`), không dùng Odoo làm UI chính.

## SoT

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| Nhập/xuất/kiểm kê NPL | Portal `kho_npl` | Không đổi UX |
| Mirror tồn + danh mục NPL | Odoo Inventory WH `NPL` | Bridge một chiều |
| Đơn / tồn thành phẩm | KiotViet (Portal lookup) | Deep-link từ hub |
| Hồ sơ BOM / costing | Portal `san_xuat` hồ sơ | Đã có |

## Menu sidebar **Sản xuất**

| Mục | URL Portal | Hành vi |
|-----|------------|---------|
| Tổng quan | `/san-xuat/tong-quan/` | KPI nhẹ + lối tắt |
| Đơn đặt hàng | `/san-xuat/don-hang/` | → KiotViet đơn |
| Kế hoạch SX | `/san-xuat/ke-hoach/` | Stub |
| Điều phối | `/san-xuat/dieu-phoi/` | Stub |
| QC | `/san-xuat/chat-luong/` | Stub |
| Giá thành KH | `/san-xuat/gia-thanh/` | → Hồ sơ SX |
| Kho sản phẩm | `/san-xuat/kho-san-pham/` | → KiotViet tồn |
| Kho NPL | `/san-xuat/kho-npl/` | → `kho_npl` tồn |
| Quy trình | `/san-xuat/quy-trinh/` | Stub + link hồ sơ |
| Hồ sơ / BOM / Costing | `/san-xuat/ho-so/` | Giữ nguyên |

## Code

- [`san_xuat/views_hub.py`](../../san_xuat/views_hub.py)
- [`san_xuat/urls.py`](../../san_xuat/urls.py)
- Migration quyền: `hrm/migrations/0062_seed_san_xuat_hub_menus.py`

## Odoo

Addon `justplay_sx` có thể vẫn cài trên ERP nhưng **không** là nơi thao tác hàng ngày. Mirror NPL: [`npl-odoo-bridge.md`](../integrations/npl-odoo-bridge.md).
