# Odoo 18 pilot — Map dữ liệu demo `justplay_pilot`

> DB: `justplay_pilot` · URL: https://erp.justplay.vn/  
> Prefix mọi mã demo: **`JP-DEMO`**  
> Scripts: `odoo/scripts/` · Chạy all: `scripts/vps-seed-odoo-all-demo.sh`

---

## 1. Thứ tự seed (bắt buộc)

| # | Script | Marker / idempotent |
|---|--------|---------------------|
| 1 | `seed_mrp_demo_data.py` | Bỏ qua nếu đã có `JP-DEMO-TP-001` |
| 2 | `seed_stock_demo_data.py` | Luôn cập nhật `STOCK_TARGETS` |
| 3 | `seed_odoo_pilot_demo.py` | Marker `justplay.odoo_pilot_demo_v1` |
| 4 | `seed_odoo_pilot_demo_expand.py` | Marker `justplay.odoo_pilot_demo_v2` (chạy lại được) |

```bash
# Trên VPS
cd /opt/odoo && bash /opt/portaljustplay/scripts/vps-seed-odoo-all-demo.sh
```

---

## 2. Sản phẩm (Inventory / MRP)

### 2.1 Nguyên liệu & bao bì (`JP-DEMO-NPL-*`)

| Mã | Tên | UoM | Nguồn script |
|----|-----|-----|--------------|
| NPL-001 | Vải cotton đỏ 180gsm | m | mrp |
| NPL-002 | Chỉ may polyester đỏ | cái | mrp |
| NPL-003 | Nhãn mác JustPlay | cái | mrp |
| NPL-004 | Dây kéo zipper 20cm | cái | mrp |
| NPL-005 | Vải cotton đen 180gsm | m | stock |
| NPL-006 | Vải cotton trắng 180gsm | m | stock |
| NPL-007 | Nút nhựa 12mm trắng | cái | stock |
| NPL-008 | Túi OPP đóng gói áo | cái | stock |
| NPL-009 | Thùng carton 40×30×25 | cái | stock |
| NPL-010 | Vải cotton xanh navy 180gsm | m | expand |
| NPL-011 | Vải thun 2 chiều ghi | m | expand |
| NPL-012 | Dây thun lưng 3cm | m | expand |
| NPL-013 | Keo dán nhãn | cái | expand |
| NPL-014 | Mực in logo JustPlay | cái | expand |
| NPL-015 | Bao thơm chống ẩm | cái | expand |

**Cấu hình chung:** `type=consu`, `is_storable=True`, category Nguyên liệu / Bao bì.

### 2.2 Thành phẩm (`JP-DEMO-TP-*`)

| Mã | Tên | Giá bán | Route Manufacture | BoM |
|----|-----|---------|-------------------|-----|
| TP-001 | Áo thun đỏ size M | 189k | ✓ (mrp) | ✓ đầy đủ + operations |
| TP-002 | Áo thun đen size L | 199k | — | expand |
| TP-003 | Áo thun trắng size M | 189k | — | expand |
| TP-004 | Áo thun đỏ size S | 179k | — | — |
| TP-005 | Áo thun navy size M | 199k | ✓ expand | expand |
| TP-006 | Áo thun ghi size L | 189k | ✓ expand | — |
| TP-007 | Áo thun đỏ size XL | 209k | ✓ expand | expand |
| TP-008 | Áo thun trắng size S | 179k | ✓ expand | — |
| TP-009 | Áo polo đỏ size M | 259k | ✓ expand | expand |
| TP-010 | Áo polo đen size L | 269k | ✓ expand | — |

### 2.3 Tồn kho mục tiêu (sau expand)

Tất cả tại **kho chính** (`wh.lot_stock_id`). Số lượng điển hình:

| Nhóm | Mã | Qty |
|------|-----|-----|
| Vải | NPL-001 … 011 | 390–1200 m |
| Phụ liệu | NPL-002 … 004, 007–009 | 180–3800 |
| Thành phẩm | TP-001 … 010 | 68–220 cái |

Chi tiết đầy đủ: `STOCK_TARGETS` trong `seed_stock_demo_data.py` và `seed_odoo_pilot_demo_expand.py`.

---

## 3. Manufacturing (MRP)

### 3.1 Work centers

| Code | Tên | Chi phí/giờ (demo) | Thiết bị BT |
|------|-----|-------------------|-------------|
| WC-CUT | Tổ cắt | 45k | EQ-003 (dao cắt) |
| WC-SEW1 | Chuyền may 1 | 35k | EQ-001 |
| WC-SEW2 | Chuyền may 2 | 35k | EQ-002 |
| WC-FIN | Hoàn thiện — ủi đóng gói | 35k | EQ-004 |

### 3.2 BoM có operations (TP-001)

| Operation | Work center | time_cycle (phút) |
|-----------|-------------|-------------------|
| Cắt vải theo rập | WC-CUT | 3 |
| May thân áo | WC-SEW1 | 8 |
| Overlock viền tay/cổ | WC-SEW2 | 5 |
| Ủi — đóng gói | WC-FIN | 4 |

**Components / 1 áo:** 1.2m vải đỏ + 1 chỉ + 1 nhãn + 1 zipper.

### 3.3 BoM chỉ components (expand)

| FG | Components |
|----|------------|
| TP-005 | 1.2m NPL-010 + NPL-002 + NPL-003 |
| TP-002 | 1.2m NPL-005 + NPL-002 + NPL-003 + NPL-004 |
| TP-003 | 1.2m NPL-006 + NPL-002 + NPL-003 |
| TP-007 | 1.3m NPL-001 + NPL-002 + NPL-003 + NPL-004 |
| TP-009 | 1.4m NPL-001 + NPL-002 + NPL-004 + NPL-003 |

### 3.4 Manufacturing Orders

| Origin | SP | Qty | Trạng thái demo | Script |
|--------|-----|-----|----------------|--------|
| JP-DEMO-MO-DRAFT | TP-001 | 80 | Draft | mrp |
| JP-DEMO-MO-PLAN | TP-001 | 120 | Confirmed | mrp |
| JP-DEMO-MO-WIP | TP-001 | 60 | Confirmed + WO started | mrp |
| JP-DEMO-MO-004 | TP-002 | 150 | Confirmed | expand |
| JP-DEMO-MO-005 | TP-003 | 100 | Confirmed + started | expand |
| JP-DEMO-MO-006 | TP-005 | 200 | Confirmed | expand |
| JP-DEMO-MO-007 | TP-009 | 80 | Draft | expand |
| JP-DEMO-MO-008 | TP-001 | 250 | Confirmed + started | expand |
| JP-DEMO-MO-009 | TP-007 | 90 | Confirmed | expand |

**Tra cứu Odoo:** Manufacturing → Operations → Manufacturing Orders → filter `Origin` contains `JP-DEMO`.

---

## 4. Purchase

### 4.1 Nhà cung cấp

| Ref | Tên |
|-----|-----|
| JP-DEMO-SUP-001 | Công ty TNHH Vải Việt |
| JP-DEMO-SUP-002 | Phụ liệu May Minh Phát |
| JP-DEMO-SUP-003 | Thiết bị Juki Việt Nam |
| JP-DEMO-SUP-004 | Dệt may Đông Phương |
| JP-DEMO-SUP-005 | In ấn Logo Pro |
| JP-DEMO-SUP-006 | Bao bì Bình Minh |

### 4.2 Purchase Orders

| Origin | NCC | SP / qty | Confirm | Receipt |
|--------|-----|----------|---------|---------|
| PO-DRAFT | SUP-001 | NPL-001 × 200 | ✗ | — |
| PO-OPEN | SUP-002 | NPL-003 × 500 | ✓ | Chờ |
| PO-RCV | SUP-001 | NPL-005 × 150 | ✓ | **Đã validate** |
| PO-004 … 010 | mixed | multi-line | mixed | expand |

**Luồng demo PO-RCV:** Confirm → Receipt validate → tồn NPL-005 tăng (minh họa Received qty billing).

---

## 5. Maintenance

### 5.1 Categories

- Máy may JustPlay
- Máy cắt & hoàn thiện (expand)

### 5.2 Equipment ↔ Work center

| Serial | Thiết bị | WC |
|--------|----------|-----|
| JK-DEMO-8700-01 | Máy may Juki DDL-8700 — Chuyền 1 | WC-SEW1 |
| PG-DEMO-M832-02 | Máy overlock Pegasus M832 | WC-SEW2 |
| EM-DEMO-625-03 | Máy cắt dao rung Eastman | WC-CUT |
| VT-DEMO-9210-04 | Bàn ủi hơi Veit | WC-FIN |
| + 6 máy expand | Juki, Tajima, Gerber, … | (một số chưa gắn WC) |

### 5.3 Maintenance requests (`JP-DEMO-MR-*`)

| Name | Loại | Mô tả ngắn | Priority |
|------|------|------------|----------|
| MR-001 | Corrective | Dao cắt kém | 3 |
| MR-002 | Preventive | Bảo dưỡng van hơi | 1 |
| MR-003 | Corrective | Tiếng kêu đầu máy | 3 |
| MR-004 … 011 | mixed | expand batch | 1–3 |

**Tra cứu:** Maintenance → Maintenance Requests; Calendar view theo `schedule_date`.

---

## 6. Accounting & Sales (chứng từ demo)

Module **Account** — hóa đơn không bắt buộc link PO/SO (tạo trực tiếp).

### 6.1 Khách hàng

| Ref | Tên |
|-----|-----|
| JP-DEMO-CUS-001 | Cửa hàng JustPlay Quận 1 |
| JP-DEMO-CUS-002 | Đại lý Thời trang An Phát |
| JP-DEMO-CUS-003 … 006 | expand (Thủ Đức, Fashion Hub, TMĐT, XK) |

### 6.2 Vendor bills (`in_invoice`)

| Ref | NCC | SP | Qty |
|-----|-----|-----|-----|
| BILL-001 | SUP-001 | NPL-001 | 120 |
| BILL-002 | SUP-002 | NPL-008 | 300 |
| BILL-003 … 006 | expand | mixed | expand |

### 6.3 Customer invoices (`out_invoice`)

| Ref | KH | SP | Qty |
|-----|-----|-----|-----|
| INV-001 | CUS-001 | TP-001 | 40 |
| INV-002 … 006 | expand | TP-002 … TP-009 | expand |

Xem chi tiết luồng: [accounting-sales.md](./accounting-sales.md).

---

## 7. Sơ đồ luồng dữ liệu demo

```text
                    ┌─────────────┐
                    │  NCC (SUP)  │
                    └──────┬──────┘
                           │ PO (JP-DEMO-PO-*)
                           ▼
┌──────────┐  Receipt   ┌──────────────┐  consume   ┌─────────────┐
│ NVL tồn  │◄───────────│   Inventory  │───────────►│  MO (MRP)   │
│ NPL-*    │            │  stock.quant │            │ JP-DEMO-MO  │
└──────────┘            └──────┬───────┘            └──────┬──────┘
                               │                           │
                               │ TP tồn                    │ WC + Equipment
                               ▼                           ▼
                        ┌──────────────┐            ┌─────────────┐
                        │ Thành phẩm   │            │ Maintenance │
                        │ JP-DEMO-TP   │            │ MR-*        │
                        └──────┬───────┘            └─────────────┘
                               │
                               │ out_invoice (INV-*)
                               ▼
                        ┌──────────────┐
                        │ KH (CUS)     │
                        └──────────────┘
```

---

## 8. Map với Portal JustPlay (tương lai)

| Odoo pilot | Portal hiện tại | Ghi chú |
|------------|-----------------|---------|
| `JP-DEMO-NPL-*` | `kho_npl` app | Demo song song — **bridge thật:** `npl_odoo_push` (`Material.code` → `default_code`) |
| Products NVL live | `kho_npl.Material` + `StockBalance` | One-way Portal→Odoo; root category `Kho NPL`, WH `KHO-NPL` — xem `docs/integrations/npl-odoo-bridge.md` |
| MO / ca SX | `reports` production hourly | Báo cáo Portal ≠ MO Odoo |
| Equipment IT | `equipment` app | Khác Maintenance Odoo (máy xưởng) |
| SSO user | `audit/odoo_sso.py` | Đã có redirect ERP |

---

## 9. Checklist kiểm tra sau seed

- [ ] Inventory → Products: filter `default_code` contains `JP-DEMO` → ≥ 25 SP
- [ ] Inventory → Reporting → Stock: có tồn > 0
- [ ] Manufacturing → MO: ≥ 9 lệnh `JP-DEMO-MO`
- [ ] Purchase → PO: ≥ 10 đơn `JP-DEMO-PO`
- [ ] Maintenance → Equipment: ≥ 10 máy; Requests ≥ 11
- [ ] Accounting → Bills/Invoices: ref `JP-DEMO-BILL` / `JP-DEMO-INV`
- [ ] Config parameter `justplay.odoo_pilot_demo` = `justplay.odoo_pilot_demo_v2`

---

## 10. File script tham chiếu

| File | Đường dẫn repo |
|------|----------------|
| MRP seed | `odoo/scripts/seed_mrp_demo_data.py` |
| Stock seed | `odoo/scripts/seed_stock_demo_data.py` |
| Pilot v1 | `odoo/scripts/seed_odoo_pilot_demo.py` |
| Pilot expand | `odoo/scripts/seed_odoo_pilot_demo_expand.py` |
| Shell all | `scripts/vps-seed-odoo-all-demo.sh` |
