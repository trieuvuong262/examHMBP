# Hub Sản xuất trên Portal (SoT)

UX vận hành chính nằm trên **Portal** (`/san-xuat/`), không dùng Odoo làm UI chính.

## SoT

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| Nhập/xuất/kiểm kê NPL | Portal `kho_npl` | Không đổi UX |
| Mirror tồn + danh mục NPL | Odoo Inventory WH `NPL` | Bridge một chiều |
| Đơn / tồn thành phẩm | KiotViet (tồn TP) + **ĐĐH SX = Portal** | `/san-xuat/don-hang/` |
| Hồ sơ BOM / costing | Portal `san_xuat` hồ sơ | Đã có |

## Menu sidebar **Sản xuất**

| Mục | URL Portal | Hành vi |
|-----|------------|---------|
| Tổng quan | `/san-xuat/tong-quan/` | KPI nhẹ + lối tắt |
| Đơn đặt hàng | `/san-xuat/don-hang/` | CRUD Portal — [don-dat-hang.md](./don-dat-hang.md) |
| **Kế hoạch sản xuất** (nhóm) | `/san-xuat/ke-hoach/` | Landing 5 mục — thiết kế: [ke-hoach-san-xuat.md](./ke-hoach-san-xuat.md) |
| → Kế hoạch tổng thể | `/san-xuat/ke-hoach/tong-the/` | Stub → P0/P1 |
| → Kế hoạch chi tiết | `/san-xuat/ke-hoach/chi-tiet/` | Stub → P4 |
| → Kế hoạch NPL | `/san-xuat/ke-hoach/npl/` | Stub → P2 |
| → Yêu cầu mua NPL | `/san-xuat/ke-hoach/yeu-cau-mua-npl/` | Stub → P3 |
| → Đơn mua hàng | `/san-xuat/ke-hoach/don-mua-hang/` | Stub (+ link KV phiếu nhập) → P5 mỏng |
| Điều phối (nhóm) | `/san-xuat/dieu-phoi/` | Landing — thiết kế: [dieu-phoi.md](./dieu-phoi.md) |
| → Lệnh sản xuất | `/san-xuat/dieu-phoi/lenh-sx/` | Stub → D0 |
| → Lệnh tháo dỡ | `/san-xuat/dieu-phoi/lenh-thao-do/` | Stub → D6 |
| → Lịch sản xuất | `/san-xuat/dieu-phoi/lich-sx/` | Stub → D4 (view từ LSX) |
| → Yêu cầu xuất vật tư | `/san-xuat/dieu-phoi/yeu-cau-xuat-vt/` | Stub → D1 (+ `kho_npl` phiếu xuất) |
| → Thống kê sản xuất | `/san-xuat/dieu-phoi/thong-ke-sx/` | Stub → D2 |
| → Yêu cầu nhập thành phẩm | `/san-xuat/dieu-phoi/yeu-cau-nhap-tp/` | Stub → D3 (+ link KV) |
| → NPL thừa | `/san-xuat/dieu-phoi/npl-thua/` | Stub → D6 |
| → Bàn giao bán thành phẩm | `/san-xuat/dieu-phoi/ban-giao-btp/` | Stub → D5 |
| → Trả lại bán thành phẩm | `/san-xuat/dieu-phoi/tra-lai-btp/` | Stub → gộp handover rejected |
| → Tình hình bàn giao SX | `/san-xuat/dieu-phoi/tinh-hinh-ban-giao/` | Stub → D5 filter |
| Kiểm tra chất lượng (nhóm) | `/san-xuat/chat-luong/` | Landing — thiết kế: [kiem-tra-chat-luong.md](./kiem-tra-chat-luong.md) |
| → Yêu cầu kiểm tra | `/san-xuat/chat-luong/yeu-cau/` | Stub → Q1 |
| → Phiếu kiểm tra | `/san-xuat/chat-luong/phieu/` | Stub → Q2/Q3 |
| → Tiêu chí chất lượng | `/san-xuat/chat-luong/tieu-chi/` | Stub → Q0 (nhóm Tiêu chuẩn) |
| → Nhóm tiêu chí CL | `/san-xuat/chat-luong/nhom-tieu-chi/` | Stub → Q0 |
| → Phương pháp chọn mẫu | `/san-xuat/chat-luong/chon-mau/` | Stub → Q0 |
| → Bộ tiêu chuẩn KTCL | `/san-xuat/chat-luong/bo-tieu-chuan/` | Stub → Q0 |
| → Lỗi KTCL | `/san-xuat/chat-luong/loi/` | Stub → Q0 |
| → Nhóm lỗi KTCL | `/san-xuat/chat-luong/nhom-loi/` | Stub → Q0 |
| Giá thành kế hoạch (nhóm) | `/san-xuat/gia-thanh/` | Landing — thiết kế: [gia-thanh-ke-hoach.md](./gia-thanh-ke-hoach.md) |
| → Giá thành định mức SP | `/san-xuat/gia-thanh/dinh-muc/` | Stub → C0/C1 (SoT chi tiết: Hồ sơ Costing) |
| → Giá thành KH theo đơn | `/san-xuat/gia-thanh/theo-don/` | Stub → C2 |
| Kho sản phẩm (nhóm — nhúng KV) | `/san-xuat/kho-san-pham/` | Landing |
| → Hàng hoá | `/san-xuat/kho-san-pham/hang-hoa/` | Cùng UI KiotViet |
| → Tồn kho | `/san-xuat/kho-san-pham/ton-kho/` | Cùng UI KiotViet |
| → Phiếu nhập | `/san-xuat/kho-san-pham/phieu-nhap/` | Cùng UI KiotViet |
| Kho NPL (nhóm — menu chuyển vào Sản xuất) | URL `/kho-npl/…` giữ nguyên | Cùng UI + data + quyền `kho_npl` |
| → Tổng quan, Danh mục, Tồn, Thẻ kho, Phiếu… | như module kho_npl | Không đổi view |
| KiotViet (nhóm — menu chuyển vào Sản xuất) | URL `/kiotviet/…` giữ nguyên | Menu độc lập ẩn nếu có `san_xuat` |
| → KH, Đơn, HĐ, Hàng hoá, Tồn, Phiếu nhập | như module kiotviet | Không đổi view |
| Quy trình | `/san-xuat/quy-trinh/` | Stub |
| Hồ sơ SX / BOM / Costing | `/san-xuat/ho-so/` | Đã có (menu riêng) |

## Code

- [`san_xuat/views_hub.py`](../../san_xuat/views_hub.py)
- [`san_xuat/urls.py`](../../san_xuat/urls.py)
- Migration quyền: `hrm/migrations/0062_seed_san_xuat_hub_menus.py`

## Odoo

Addon `justplay_sx` có thể vẫn cài trên ERP nhưng **không** là nơi thao tác hàng ngày. Mirror NPL: [`npl-odoo-bridge.md`](../integrations/npl-odoo-bridge.md).
