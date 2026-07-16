# Bridge NPL → Odoo (Portal = SoT)

Một chiều: **Portal `kho_npl` = nguồn sự thật** → Odoo Inventory mirror.

| Portal | Odoo |
|--------|------|
| `Material.code` | `product.product.default_code` |
| `MaterialCategory` | `product.category` dưới root **Kho NPL** |
| Warehouse cố định | `NPL` |
| `WarehouseLocation` | `stock.location` con |
| `StockBalance` | `stock.quant` (inventory mode) |
| `Supplier.code` | `res.partner.ref` (`supplier_rank=1`) |
| `Material.supplier` | `product.supplierinfo` (vendor trên product) |

Không ghi ngược Portal trong phase này. Thao tác nhập/xuất/chuyển vẫn làm trên Portal.

## Yêu cầu

- Odoo đã cài app **Inventory** (`stock`) — và `purchase` nếu cần vendor pricelist.
- Env XML-RPC: `ODOO_URL`, `ODOO_DB`, `ODOO_API_USER`, `ODOO_API_PASSWORD`.

Script cài Inventory (VPS): `odoo/scripts/install_stock_for_npl.sh`.

## CLI vận hành

```bash
# Đối chiếu (chỉ đọc)
python manage.py npl_odoo_reconcile
python manage.py npl_odoo_reconcile --show missing_in_odoo --show-limit 50

# Dry-run toàn bộ (không ghi)
python manage.py npl_odoo_push

# Full push danh mục + NCC + tồn (Phase 1)
python manage.py npl_odoo_push --apply

# Thử ít mã
python manage.py npl_odoo_push --apply --limit 20

# Chỉ danh mục, không tồn
python manage.py npl_odoo_push --apply --no-stock

# Vài mã cụ thể
python manage.py npl_odoo_push --apply --codes JP-VAI-COT180-WHT --codes JP-CHI-PES40-WHT
```

### VPS (Portal container)

```bash
# Sau khi scp kho_npl/odoo_bridge.py (+ commands) lên /opt/portaljustplay/
bash /opt/portaljustplay/scripts/vps-full-push-npl-odoo.sh
```

Hoặc thủ công: `docker cp` vào `portaljustplay-web-1:/app/kho_npl/…` rồi chạy `npl_odoo_push --apply`.

## Smoke ERP

1. Apps → Inventory đã cài.
2. Products → filter category **Kho NPL**.
3. Inventory → On Hand theo location (barcode = mã vị trí Portal).
4. Warehouses → code **NPL**.
5. Contacts → filter suppliers / `ref` = mã NCC Portal.

## Code

- [`kho_npl/odoo_bridge.py`](../../kho_npl/odoo_bridge.py)
- Plan gốc: [`npl-odoo-bridge-plan.md`](./npl-odoo-bridge-plan.md)

## Lưu ý Phase 1

- Root **Kho NPL** tách biệt root **KiotViet** (thành phẩm).
- Chạy lại an toàn (idempotent theo `default_code` / `partner.ref`).
- Portal UX kho_npl không đổi.

## Phase sau (chưa implement)

| Phase | Nội dung |
|-------|----------|
| **P2** | `MaterialBatch` → `stock.lot` (name = batch code); lot cost chi tiết |
| **P3** | Khi Portal post/approve/close → `stock.picking` / scrap / inventory apply; map idempotent `odoo_picking_id` / `NplOdooDocLink`; không sửa chứng từ đã sync trên Odoo |
| **P4** | Hook/queue gần realtime + reconcile định kỳ |

Ngoài phạm vi: dual-write Odoo→Portal, clone UI Django sang Odoo, Quality/MRP (sau khi mirror NPL ổn).
