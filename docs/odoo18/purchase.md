# Odoo 18 — Purchase (Mua hàng)

> Nguồn: [Odoo 18 Purchase documentation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase.html)  
> Mục đích: tham chiếu RFQ/PO, vendor, replenishment, hóa đơn NCC tại JustPlay.

---

## 1. Vai trò module

Purchase quản lý **mua hàng từ NCC**:

- **RFQ** (Request for Quotation) → **PO** (Purchase Order)
- **Vendor pricelist** — giá & lead time theo NCC
- Tích hợp **Inventory** (receipt) và **Accounting** (vendor bills)
- Blanket orders, call for tenders, templates, báo cáo

---

## 2. Cây tài liệu Odoo 18 (Purchase)

### Products
- Import vendor pricelist
- Configure reordering rules (liên kết Inventory)
- Temporary reordering rules

### Manage deals
- Requests for quotation
- Blanket orders
- Call for tenders
- Purchase templates
- **Bill control policies**
- **Manage vendor bills**

### Advanced
- Purchase Analysis, Vendor costs, Procurement expenses reports
- EDI purchase-to-sales order import

---

## 3. Cấu hình sản phẩm mua

**Menu:** Purchase → Products → Products

| Thiết lập | Bắt buộc |
|-----------|----------|
| **Purchase** (checkbox) | Có |
| Tab **Inventory** → route **Buy** | Có (khi dùng Inventory) |
| Tab **Purchase** → vendor lines | Vendor, Unit Price, **Delivery Lead Time** |

### Vendor pricelist line
- Quantity breaks
- Vendor Product Code, Discount %
- **Delivery Lead Time** — dùng cho Expected Arrival & reordering JIT

**Hoặc:** Purchase → Configuration → Vendor Pricelists

---

## 4. RFQ / PO — vòng đời

**Menu:** Purchase → Orders → Requests for Quotation

### Dashboard
- To Send / Waiting / Late
- Filters, group by

### Tạo RFQ (New)
| Field | Ý nghĩa |
|-------|---------|
| **Vendor** | NCC |
| **Vendor Reference** | Số SO/DO phía NCC |
| **Order Deadline** | Hạn NCC xác nhận — quá hạn = Late |
| **Expected Arrival** | Auto từ deadline + lead time |
| **Ask confirmation** | Email xác nhận ngày ship |
| **Deliver to** | Warehouse receipt / **Dropship** (cần bật Dropshipping) |

### Products tab
- Add product, qty, unit price
- Catalog — chọn từ catalog NCC
- Create & edit — tạo SP mới inline

### Gửi & xác nhận
- **Send by Email** → RFQ Sent
- **Print RFQ** → PDF
- **Confirm Order** → **PO** (+ Confirmation Date)

### Sau confirm
- **Receipt** smart button (Inventory) — WH/IN chờ validate
- **Receive Products** trên PO
- Chatter — email & lịch sử

---

## 5. Tích hợp Inventory

```
RFQ/PO Confirm ──► Receipt (incoming shipment)
Validate Receipt ──► On-hand ↑ (tracked products)
Reordering (Buy) ──► Auto RFQ/PO
MTO + Buy ──► PO gắn SO (smart button)
```

**Dropship:** Deliver to = Dropship + địa chỉ KH — không qua kho mình (cần Inventory Dropshipping setting).

---

## 6. Bill control policies

**Menu:** Purchase → Configuration → Settings → Invoicing

| Policy | Vendor bill khi nào |
|--------|---------------------|
| **Ordered quantities** | Ngay khi **confirm PO** — theo qty đặt |
| **Received quantities** | Sau khi **nhận hàng** (toàn bộ hoặc một phần) — theo qty received |

Override per product: tab Purchase → **Control Policy**

### 3-way matching
- Chỉ thanh toán khi **đã nhận hàng** (khớp PO – receipt – bill)
- **Chỉ hoạt động đúng với Received quantities**
- Purchase → Settings → tick 3-way matching

---

## 7. Vendor bills (hóa đơn NCC)

**Doc:** [Manage vendor bills](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/manage.html)

### Từ PO
- **Create Bill** trên PO
- Ordered qty: bill ngay cả khi chưa nhận
- Received qty: phải validate receipt trước (ít nhất partial)

### Từ Accounting
- Accounting → Vendors → Bills → New (không cần PO)
- **Auto-Complete** — link PO có sẵn

### Thanh toán
- Confirm bill → Register Payment

### Batch billing
- Chọn nhiều bills → Register Payment hàng loạt

---

## 8. Thỏa thuận mua nâng cao

| Công cụ | Dùng khi |
|---------|----------|
| **Blanket order** | Hợp đồng khung giá/số lượng kỳ hạn — cần bật Settings |
| **Call for tenders** | So giá nhiều NCC |
| **Purchase templates** | RFQ mẫu lặp lại |

---

## 9. Replenishment tự động (góc nhìn Purchase)

| Nguồn | Kết quả |
|-------|---------|
| Reordering rule (Buy, Auto) | RFQ/PO khi forecast < Min |
| Reordering (Manual) | User Order trên Replenishment |
| MTO + Buy | PO mỗi SO confirm |
| 0/0/1 + Buy | PO từng đơn vị |

**Scheduler:** mặc định 1 lần/ngày — RFQ có thể chưa gửi email cho đến khi user Send.

---

## 10. Báo cáo

- **Purchase Analysis** — giá trị mua, NCC, sản phẩm
- **Vendor costs**
- **Procurement expenses**

---

## 11. Tích hợp chéo JustPlay

```
Portal đề xuất mua / kho NPL ──► (tương lai) RFQ/PO Odoo?
Inventory reordering ──► PO ──► Receipt ──► NVL cho MO
MRP subcontracting ──► PO dạng mua TP gia công
Accounting ──► vendor bill, 3-way match
```

Pilot: **10+ PO** `JP-DEMO-PO-*` (draft / confirmed / received). Map: [pilot-demo-map.md §4](./pilot-demo-map.md#4-purchase).

---

## 12. Checklist thiết kế JustPlay

### Master data NCC
- [ ] Vendor trên Contacts (Purchase rank)
- [ ] Pricelist: giá, lead time, MOQ
- [ ] Tiền tệ (nếu mua ngoại tệ)

### Quy trình
- [ ] RFQ bắt buộc hay confirm PO thẳng?
- [ ] Bill policy: Ordered vs Received?
- [ ] 3-way matching có bật không?

### Kho
- [ ] Receipt 1-step hay QC trước kho?
- [ ] Dropship có dùng không?

### Tự động hóa
- [ ] Reordering rules sản phẩm A,B,C
- [ ] Ai duyệt PO (approval — có thể cần Studio/Enterprise hoặc quy trình ngoài)

---

## 13. Link doc ưu tiên

| Chủ đề | URL |
|--------|-----|
| RFQ | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/rfq.html |
| Vendor bills | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/purchase/manage_deals/manage.html |
| Reordering (Inventory) | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html |

---

## 14. So sánh nhanh RFQ vs PO

| | RFQ | PO |
|--|-----|-----|
| Trạng thái | Nháp gửi NCC | Đã cam kết mua |
| Receipt | Chưa (cho đến confirm) | Có document chờ nhận |
| Sửa giá/qty | Trước confirm | Hạn chế sau confirm |
