# Odoo 18 — Sales & Accounting (Kế toán / Bán hàng)

> Nguồn: [Odoo 18 Sales](https://www.odoo.com/documentation/18.0/applications/sales.html) · [Accounting](https://www.odoo.com/documentation/18.0/applications/finance/accounting.html)  
> Pilot JustPlay: module **Account** đã seed hóa đơn demo; **Sales** chưa seed SO — chỉ hóa đơn bán trực tiếp.

---

## 1. Vai trò trong chuỗi cung ứng JustPlay

```text
Sales (SO) ──► Delivery (Stock) ──► Customer invoice
Purchase (PO) ──► Receipt (Stock) ──► Vendor bill
Manufacturing (MO) ──► FG stock ──► COGS / valuation (Accounting)
```

Pilot hiện tại tập trung **Inventory + MRP + Purchase + Maintenance**. Accounting dùng để **minh họa hóa đơn**; Sales mở rộng phase sau.

---

## 2. Sales — bán hàng

### 2.1 Quotation → Sales Order

**Menu:** Sales → Orders → Quotations

| Bước | Hành động |
|------|-----------|
| New | Chọn Customer, sản phẩm `JP-DEMO-TP-*`, qty, giá |
| Send | Gửi báo giá |
| Confirm | → **Sales Order** |

### 2.2 Tích hợp Inventory

- SP thành phẩm `is_storable=True` → Confirm SO tạo **Delivery Order**
- Route **MTO** trên SP: SO confirm → trigger MO (xem [inventory.md](./inventory.md))
- Validate delivery → giảm tồn TP

### 2.3 Tích hợp Accounting

- **Invoice policy** (product hoặc settings):
  - **Ordered quantities** — hóa đơn khi confirm SO
  - **Delivered quantities** — hóa đơn sau khi giao hàng

### 2.4 Chưa có trong pilot demo

Chưa seed `sale.order`. Khi mở rộng:

```python
# Gợi ý origin: JP-DEMO-SO-001
# Customer: JP-DEMO-CUS-001
# Line: JP-DEMO-TP-001 × 40 → confirm → delivery → invoice
```

---

## 3. Accounting — kế toán

### 3.1 Loại chứng từ

| move_type | Tiếng Việt | Đối tác |
|-----------|------------|---------|
| `out_invoice` | Hóa đơn bán | Customer |
| `in_invoice` | Hóa đơn mua (NCC) | Vendor |
| `out_refund` / `in_refund` | Hoàn tiền | |

### 3.2 Vendor bill — từ Purchase

**Doc:** [Manage vendor bills](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/manage.html)

| Cách tạo | Khi nào |
|----------|---------|
| **Create Bill** trên PO | Chuẩn — link PO |
| Accounting → Bills → New + Auto-Complete | Bill không qua PO |
| Batch Register Payment | Thanh toán nhiều bill |

**Bill control** (Purchase settings): Ordered vs Received qty — xem [purchase.md](./purchase.md).

### 3.3 Customer invoice — từ Sales hoặc trực tiếp

Pilot seed tạo **trực tiếp** `account.move` với `ref=JP-DEMO-INV-*` (không qua SO).

### 3.4 Trạng thái chứng từ

Draft → **Posted** (`action_post`) → Register Payment → Paid

Seed script gọi `action_post()`; lỗi chart of accounts in ra cảnh báo nhưng vẫn tạo draft.

---

## 4. Dữ liệu demo pilot (Accounting)

Chi tiết bảng: [pilot-demo-map.md §6](./pilot-demo-map.md#6-accounting--sales-chứng-từ-demo)

| Ref | Loại | Đối tác | Sản phẩm |
|-----|------|---------|----------|
| JP-DEMO-BILL-001 | Vendor bill | Vải Việt | NPL-001 |
| JP-DEMO-BILL-002 | Vendor bill | Minh Phát | NPL-008 |
| JP-DEMO-INV-001 | Customer invoice | CH Q1 | TP-001 |
| + BILL/INV 003–006 | expand | mixed | mixed |

**Script:** `seed_odoo_pilot_demo.py` → `seed_accounting()`; expand → `seed_accounting_extra()`.

---

## 5. Valuation tồn kho (liên kết Inventory)

Odoo 18 Community với **Inventory + Accounting**:

- **Standard price** (`standard_price`) trên product — demo đã set (VD TP-001 cost ~88–98k)
- Khi validate MO / receipt → journal entries (tùy cấu hình COA Vietnam)
- Báo cáo: Inventory → Reporting → **Stock Valuation**

Pilot: kiểm tra COA locale VN đã cài khi tạo DB.

---

## 6. 3-way matching (Purchase ↔ Stock ↔ Accounting)

Chỉ khi Purchase **Received quantities** + bật 3-way matching:

1. PO confirmed
2. Receipt validated
3. Vendor bill khớp qty received mới thanh toán

JustPlay checklist: quyết định policy trước khi go-live kế toán.

---

## 7. Checklist thiết kế JustPlay

### Sales (phase sau pilot)
- [ ] Có bán B2B (đại lý) vs B2C (CH) — pricelist?
- [ ] Invoice: ordered hay delivered?
- [ ] Link SO → MO (MTO) cho đơn may theo yêu cầu?

### Accounting
- [ ] COA Vietnam — chart template khi tạo DB
- [ ] Vendor bill: từ PO hay nhập tay (kế toán)?
- [ ] Customer invoice: từ SO hay POS?
- [ ] Đối soát tồn Odoo vs `kho_npl` Portal

### Demo tiếp theo
- [ ] Seed `JP-DEMO-SO-*` + delivery + invoice linked
- [ ] Link `JP-DEMO-BILL-*` từ PO thay vì tạo rời

---

## 8. Link doc ưu tiên

| Chủ đề | URL |
|--------|-----|
| Sales quotations | https://www.odoo.com/documentation/18.0/applications/sales/sales/sales_quotations.html |
| Vendor bills (Purchase) | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/manage.html |
| Accounting getting started | https://www.odoo.com/documentation/18.0/applications/finance/accounting/get_started.html |
