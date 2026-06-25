# Odoo 18 — Tài liệu tham chiếu thiết kế (JustPlay)

Bộ ghi chú nội bộ tổng hợp từ [Odoo 18.0 User Docs — Supply Chain](https://www.odoo.com/documentation/18.0/applications.html), phục vụ thiết kế pilot tại `erp.justplay.vn`.

| File | Module | Doc gốc |
|------|--------|---------|
| [inventory.md](./inventory.md) | Inventory (Kho) | [Inventory](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory.html) |
| [mrp.md](./mrp.md) | Manufacturing (MRP) | [Manufacturing](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing.html) |
| [purchase.md](./purchase.md) | Purchase (Mua hàng) | [Purchase](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase.html) |
| [maintenance.md](./maintenance.md) | Maintenance (Bảo trì) | [Maintenance](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance.html) |
| [accounting-sales.md](./accounting-sales.md) | Sales & Accounting | [Sales](https://www.odoo.com/documentation/18.0/applications/sales.html) · [Accounting](https://www.odoo.com/documentation/18.0/applications/finance/accounting.html) |
| [pilot-demo-map.md](./pilot-demo-map.md) | **Map dữ liệu demo** `justplay_pilot` | Scripts `odoo/scripts/seed_*.py` |

**Phiên bản Odoo:** 18.0 Community (pilot `erp.justplay.vn`).  
**Cập nhật:** 2026-05-28 — doc module + map demo seed + Sales/Accounting.

### Đọc nhanh theo mục đích

| Mục đích | Bắt đầu từ |
|----------|------------|
| Thiết kế nghiệp vụ | `inventory.md` → `mrp.md` → `purchase.md` → `maintenance.md` |
| Xem dữ liệu đã seed trên ERP | [pilot-demo-map.md](./pilot-demo-map.md) |
| Hóa đơn / bán hàng | [accounting-sales.md](./accounting-sales.md) |
| Chạy lại demo trên VPS | `bash /opt/portaljustplay/scripts/vps-seed-odoo-all-demo.sh` |
