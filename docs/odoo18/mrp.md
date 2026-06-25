# Odoo 18 — Manufacturing (MRP)

> Nguồn: [Odoo 18 Manufacturing documentation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing.html)  
> Mục đích: tham chiếu thiết kế LSX, BoM, work center, subcontracting tại JustPlay.

---

## 1. Vai trò module

Manufacturing quản lý **toàn bộ vòng đời sản xuất**:

- **Manufacturing Order (MO)** — lệnh sản xuất
- **Bill of Materials (BoM)** — định mức NVL + operations
- **Work Centers** — máy/chuyền; Shop Floor tablet
- **Subcontracting** — gia công ngoài
- Báo cáo: delays, allocation, OEE, production analysis

Phụ thuộc **Inventory** (component/FG locations, routes Manufacture).

---

## 2. Cây tài liệu Odoo 18 (Manufacturing)

### Basic setup
- Manufacturing product configuration
- Bill of materials
- One- / Two- / Three-step manufacturing
- Manufacturing order costs

### Advanced configuration
- BoMs for product variants
- **Kits**
- **Multilevel BoMs**
- Work centers
- Work order dependencies

### Workflows
- Master production schedule (MPS)
- Work center time off
- Scrap during manufacturing
- Manufacturing backorders
- Split and merge MOs
- Unbuild orders
- By-products
- Continuous product improvement
- Manufacture with lots/serial numbers

### Shop Floor
- Shop Floor overview, time tracking

### Subcontracting
- Basic subcontracting
- Resupply subcontracting
- Dropship to subcontractor

### Reporting
- Delays, Allocation reports, OEE, Production analysis

---

## 3. Cấu hình sản phẩm sản xuất

**Menu:** Manufacturing → Products → Products (hoặc Inventory → Products)

### Bước bắt buộc
1. Tab **Inventory** → tick route **Manufacture**
2. Tạo **BoM** (smart button Bill of Materials)
3. (Tuỳ chọn) **Track Inventory** + Lot/Serial trên FG

### Lot/Serial khi sản xuất
- Tracking = By Unique Serial Number hoặc By Lots
- Gán lot trên MO (field Lot/Serial Number) hoặc **Register Production** trên Shop Floor

### BoM cơ bản
**Menu:** Manufacturing → Products → Bills of Materials

| Field | Ý nghĩa |
|-------|---------|
| **Product** | Thành phẩm |
| **Quantity** | Số lượng output của BoM này |
| **Components** | NVL + số lượng |
| **Operations** | Tên operation + **Work Center** (cần bật Work Orders) |

**Work Orders:** Manufacturing → Configuration → Settings → Work Orders

---

## 4. Manufacturing steps (theo warehouse)

**Menu:** Inventory → Configuration → Warehouses → tab Warehouse Configuration → **Manufacture**

| Tùy chọn | Ý nghĩa |
|----------|---------|
| **Manufacture (1 step)** | MO xong → vào kho; không tạo transfer riêng pick/store component |
| **Pick components and then manufacture (2 steps)** | Pick NVL trước khi SX |
| **Pick, manufacture, then store products (3 steps)** | Pick → SX → đưa TP vào stock |

JustPlay demo: xác định xưởng có tách khu **pre-production** / **post-production** hay không.

---

## 5. Manufacturing Order (MO) — vòng đời

**Tạo MO:** Manufacturing → Operations → Manufacturing Orders → New

1. Chọn **Product** → BoM auto-fill (đổi BoM nếu nhiều BoM)
2. Bổ sung Components / Work Orders nếu cần (ngoài BoM)
3. **Confirm**
4. Hoàn thành **Work Orders** (Start → Done) hoặc Shop Floor
5. **Produce All** → MO = Done → TP vào inventory

### Shop Floor
- Work order card theo work center
- Steps + **Register Production** (số lượng OK)
- **Mark as Done** / **Close Production**

### Component Status
MO chỉ hoàn thành khi **đủ component** — quan trọng với multilevel BoM.

---

## 6. BoM types

### 6.1 BoM sản xuất thường (Manufacture)
- Components + Operations
- Confirm MO → tiêu hao NVL, nhận FG

### 6.2 Kit BoM
**Doc:** [Kits](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/kit_shipping.html)

- BoM Type = **Kit**
- Bán combo: SO 1 dòng kit; **Delivery list từng component**
- **Không** cần operations nếu chỉ bán

| | Untracked kit | Tracked kit |
|--|---------------|-------------|
| Tồn kit | Không track cấp kit | Track kit |
| Reorder | Theo **component** | Theo **component** |
| Bán khi thiếu component | **Không** bán được | Tương tự |
| Serial kit | Không — chỉ component | Không serial cấp kit |
| Internal transfer kit | **Tách** thành components | Tương tự |

**Không** điều chỉnh tồn cấp kit; giá trị tồn = tổng component.

### 6.3 Multilevel BoM
**Doc:** [Multilevel BoMs](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/sub_assemblies.html)

- **Subassembly** (BTP) có BoM riêng; FG BoM gồm BTP + linh kiện
- Xây **từ dưới lên** (component → subassembly → FG)

#### Replenishment cho subassembly (khuyến nghị Odoo)

**Option 1 (recommended):** Reordering rule **0/0/1** trên từng sublevel product (Min=0, Max=0, route Manufacture)

**Option 2:** MTO + Manufacture trên sublevel — **reserve chặt** cho MO cha; kém linh hoạt

> Sublevel MO phải **xong trước** khi chạy MO top-level.

#### Quy trình setup multilevel (tóm tắt)
1. Tạo BoM tầng thấp → cao
2. Set on-hand ban đầu (nếu có)
3. Procurement: 0/0/1 hoặc MTO cho BTP
4. Vendor / manufacturing **lead times**
5. Manufacturing steps, work centers, MPS (nếu cần)

**Kit vs Multilevel:** Kit = bán/organize; Multilevel = **thật sự sản xuất** BTP.

---

## 7. Work centers

- Máy/chuyền gắn **operations** trên BoM
- Capacity, time efficiency, OEE
- **Work center time off** — bảo trì / nghỉ
- Liên kết **Maintenance** (equipment trên work center)

JustPlay demo: đã seed work centers — map với line sản xuất thực tế.

---

## 8. Subcontracting

### Basic subcontracting
**Doc:** [Basic subcontracting](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/subcontracting/subcontracting_basic.html)

- Gia công **trọn gói**: NCC tự lo NVL + SX → giao TP
- Cấu hình:
  - Product → Purchase tab: vendor + **Delivery Lead Time** (gồm cả thời gian SX NCC)
  - BoM Type = **Subcontracting** + chọn Subcontractors
  - **Không** list components (NCC tự quản)
- Luồng: PO → chờ NCC → **Receipt** validate → TP vào stock
- Inventory moves: virtual Subcontracting Location, Production (tiêu hao/lắp ráp ảo)

### Resupply / Dropship to subcontractor
- Gửi NVL cho NCC gia công — phức tạp hơn; đọc doc riêng khi JustPlay cần

---

## 9. Workflows khác (điểm cần nhớ)

| Tính năng | Mục đích |
|-----------|----------|
| **Backorders** | MO chưa đủ qty → MO con |
| **Split/Merge MO** | Tách/gộp lệnh |
| **Unbuild** | Tháo TP về NVL |
| **By-products** | Phụ phẩm khi SX |
| **Scrap during MO** | Hao hụt trong SX |
| **MPS** | Lập kế hoạch SX thủ công theo mùa |

---

## 10. Chi phí MO

- Manufacturing order costs — NVL + operation cost
- Cần cấu hình cost trên product / work center / accounting

---

## 11. Tích hợp chéo

```
Reordering (Manufacture) ──► MO
MO Confirm ──► Reserve/consume components (Stock)
MO Done ──► FG → Stock
PO (Buy) ──► Receipt ──► components for MO
Subcontract PO ──► Receipt FG
Maintenance Block WC ──► không lên lịch WO/MO tại WC đó
Portal báo cáo SX ──► map concept: ca, sản lượng, định mức (ngoài Odoo)
```

---

## 12. Checklist thiết kế JustPlay

### Sản phẩm & BoM
- [ ] Phân loại: FG, BTP, NVL, kit bán lẻ (nếu có)
- [ ] BoM version / 1 BoM active per product?
- [ ] Operations có cần Shop Floor hay chỉ MO đơn giản?

### Lập lịch
- [ ] 1-step đủ hay cần pick NVL riêng?
- [ ] Multilevel: 0/0/1 cho BTP?
- [ ] Lead time SX trên product/BoM

### Gia công ngoài
- [ ] Có NCC gia công trọn gói → basic subcontracting

### Chất lượng / bảo trì
- [ ] Work center trùng thiết bị Maintenance
- [ ] Block WC khi bảo trì corrective

---

## 13. Link doc ưu tiên

| Chủ đề | URL |
|--------|-----|
| Product + BoM setup | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/basic_setup/configure_manufacturing_product.html |
| One-step MO | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/basic_setup/one_step_manufacturing.html |
| Kits | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/kit_shipping.html |
| Multilevel BoM | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/sub_assemblies.html |
| Basic subcontracting | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/subcontracting/subcontracting_basic.html |

---

## 14. Ghi chú pilot

| Thành phần | Demo |
|------------|------|
| Work centers | WC-CUT, WC-SEW1, WC-SEW2, WC-FIN |
| BoM + operations | `JP-DEMO-TP-001` (4 công đoạn) |
| BoM components only | TP-002, 003, 005, 007, 009 |
| MO | 9 lệnh `JP-DEMO-MO-*` (draft / confirmed / WIP) |

**Map chi tiết:** [pilot-demo-map.md §3](./pilot-demo-map.md#3-manufacturing-mrp) · Script: `seed_mrp_demo_data.py`, `seed_odoo_pilot_demo_expand.py`

Mở rộng: multilevel BTP, kit combo, subcontracting NCC.
