# Odoo 18 — Inventory (Kho / WMS)

> Nguồn: [Odoo 18 Inventory documentation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory.html)  
> Mục đích file: tham chiếu khi thiết kế kho, luồng nhập/xuất, replenishment, tích hợp MRP/Purchase tại JustPlay.

---

## 1. Vai trò module

Inventory vừa là **ứng dụng quản lý tồn kho**, vừa là **WMS** (warehouse management):

- Theo dõi tồn on-hand / forecast
- Điều phối nhập — xuất — chuyển nội bộ qua **routes** (push/pull rules)
- Tự động **replenishment** (mua hoặc sản xuất) qua reordering rules
- Định giá tồn kho, lot/serial, báo cáo

**Mọi module Supply Chain** (MRP, Purchase, Maintenance) đều dựa trên master data sản phẩm và location của Inventory.

---

## 2. Cây tài liệu Odoo 18 (Inventory)

### 2.1 Product management
- **Configure product:** Product type, UoM, Packages, Packaging
- **Product tracking:** Serial numbers, Lot numbers, Reassign lot/serial, Expiration dates
- **Inventory valuation:** Automatic valuation, Using valuation, Landed costs, Valuation by lots/serial

### 2.2 Warehouses and storage
- **Inventory management:** Warehouses, Locations, Inventory adjustments, Cycle counts, Scrap
- **Replenishment:** MTO, Reordering rules, Replenishment report, Lead times, Inter-warehouse replenishment
- **Reporting:** Forecasted, Stock, Locations dashboard, Moves history, Stock valuation dashboard

### 2.3 Shipping and receiving
- **Inbound/outbound flows:** Routes & push/pull rules, 1/2/3-step receipt & delivery, Putaway rules, Storage categories, Cross-dock, Consignment, Dropshipping
- **Delivery methods:** Carriers, labels, integrations (DHL, FedEx, …)
- **Reservation methods:** At confirmation, Manual, Before scheduled date
- **Picking methods:** Batch, Cluster, Wave transfers
- **Removal strategies:** FIFO, LIFO, FEFO, Closest location, Least packages

---

## 3. Product type — nền tảng mọi luồng

**Menu:** Inventory → Products → Products

| Thiết lập | Ý nghĩa |
|-----------|---------|
| **Sales** | Bán được (SO) |
| **Purchase** | Mua được (PO/RFQ) |
| **Product Type: Goods** | Hàng hóa vật lý — có tab Inventory |
| **Product Type: Service** | Không track tồn |
| **Track Inventory** | Bật = storable tracked; tắt = consumable/untracked |

### Tracked vs Untracked (Goods)

| Khả năng | Tracked | Untracked |
|----------|---------|-----------|
| On Hand / Forecast smart button | Có | Không |
| Reordering rules | Có | Không |
| Inventory valuation / báo cáo tồn | Có | Không |
| Đưa vào PO | Có | Có (nhận không tăng on-hand) |
| BoM / Manufacture / Kit | Có | Có |
| Lot/Serial | Có | Không |

**Tracking:** By Unique Serial Number | By Lots | By Quantity

**Invoicing policy** (cần Sales app): Ordered quantities vs Delivered quantities.

### Gợi ý JustPlay
- **NVL, bán thành phẩm, TP:** Goods + Track Inventory (+ Lot nếu cần)
- **Vật tư tiêu hao, bao bì phụ:** có thể untracked nếu không cần báo cáo tồn chính xác
- Mọi sản phẩm dùng reordering rules **bắt buộc** tracked

---

## 4. Routes — Push / Pull rules

**Bật:** Inventory → Configuration → Settings → **Multi-Step Routes** (+ Storage Locations tự bật)

### Khái niệm
- **Route:** tập hợp rules điều khiển di chuyển hàng giữa locations
- **Push rule:** khi hàng **đến** location A → tự chuyển tiếp tới B
- **Pull rule:** khi **cần** hàng tại B → kéo từ A (chạy ngược demand)

### Rule actions
| Action | Khi nào |
|--------|---------|
| **Pull From** | Cần hàng tại destination |
| **Push To** | Hàng vừa đến source |
| **Pull & Push** | Cả hai |
| **Buy** | Tạo RFQ/PO |
| **Manufacture** | Tạo MO |

### Supply method (Pull)
- **Take From Stock**
- **Trigger Another Rule**
- **Take From Stock, if Unavailable, Trigger Another Rule**

### Route áp dụng trên
Product, Product category, Warehouse, Packaging, Shipping method, **Sales order line** (chọn tay từng dòng SO).

### Warehouse steps (cấu hình tại Warehouse)
- **Incoming:** 1 / 2 / 3 bước nhận hàng
- **Outgoing:** 1 / 2 / 3 bước giao hàng  
  Ví dụ Pick-Pack-Ship: Output → Customer (delivery), Packing Zone ← Stock (pick), v.v.

**Luồng xử lý:** Odoo tạo transfer **từ bước cuối ngược về đầu** (delivery trước, pick sau).

---

## 5. Reordering rules — replenishment cốt lõi

**Menu:** Inventory → Operations → Replenishment (hoặc smart button trên product)

### Tham số chính
| Field | Ý nghĩa |
|-------|---------|
| **Min** | Dưới ngưỡng này (forecast) → kích hoạt |
| **Max** | Mức replenish tới |
| **Multiple Quantity** | Làm tròn lô đặt (vd. đặt theo thùng 5) |
| **Location** | Kho áp dụng (mặc định WH/Stock) |
| **Route** | Buy hoặc Manufacture (preferred route) |
| **Trigger** | Auto / Manual |

### Route → chứng từ sinh ra
- **Buy** → RFQ/PO (Purchase)
- **Manufacture** → MO (MRP)
- Không chọn route → lấy route trên tab Inventory của product
- Nhiều route: ưu tiên **Buy trước Manufacture** nếu không set preferred

### Trigger Auto
- Scheduler chạy (mặc định **1 lần/ngày**) hoặc confirm SO làm forecast < Min
- Dev mode: Inventory → Operations → Run Scheduler

### Trigger Manual
- Hiện trên Replenishment report; user bấm **Order**

### 0/0/1 rule (đặc biệt)
- Min=0, Max=0, To Order=1
- Mỗi SO confirm → đặt/bán xuất **1 đơn vị** (không giữ tồn)
- Khác **MTO:** không reserve chặt cho SO gốc; không có smart button SO↔PO
- Dùng cho: mua/sản xuất theo đơn nhưng linh hoạt tồn hơn MTO

### Advanced fields
- **Vendor:** RFQ tự chọn NCC
- **BoM:** MO dùng BoM cụ thể khi nhiều BoM
- **Procurement group:** gom PO/MO theo demand (SO) — bật smart button liên kết

### Just-in-time logic
- **Forecasted date** = hôm nay + tổng lead time (vendor + security + days to purchase / manufacturing)
- Chỉ hiện “To Order” khi demand nằm trong cửa sổ forecasted date
- **Visibility days:** gom thêm demand tương lai gần để giảm chi phí vận chuyểi
- **Horizon days:** chỉ với manual rules — nhìn trước X ngày

---

## 6. Replenish on Order (MTO)

**Route archived mặc định** — cần unarchive: Inventory → Configuration → Routes → filter Archived → Unarchive **Replenish on Order (MTO)**

### Cấu hình product
Tab Inventory → tick **MTO** + **Buy** hoặc **Manufacture** (bắt buộc có route thứ 2)

### Hành vi
- Confirm SO/MO → **luôn** tạo RFQ/MO (kể cả còn tồn)
- RFQ/MO **gắn smart button** với SO gốc
- Hàng replenish **reserve** cho SO đó

### Hủy SO
- Delivery hủy tự động; RFQ/MO **không** tự hủy — cần xử lý tay

### So sánh MTO vs 0/0/1 vs Reordering thường

| | MTO | 0/0/1 | Reorder Min/Max |
|--|-----|-------|-----------------|
| Gắn SO | Có (reserve) | Không | Tùy procurement group |
| Còn tồn vẫn đặt | Có | Theo rule | Chỉ khi forecast < Min |
| Phù hợp JustPlay | Make-to-order chặt | Linh hoạt hơn | NVL/TP chạy tồn an toàn |

---

## 7. Warehouse & locations

- **Warehouse:** entity có incoming/outgoing routes riêng
- **Locations:** internal / supplier / customer / inventory loss / production / subcontracting…
- **Inventory adjustments:** điều chỉnh số lượng thực tế
- **Cycle counts:** kiểm kê định kỳ
- **Scrap:** hủy hàng hỏng

**Putaway rules:** chỉ định kệ/khu khi nhận hàng  
**Storage categories:** giới hạn capacity theo sản phẩm

---

## 8. Nhập / xuất chuẩn

### Receipt (từ PO)
Confirm PO → tự tạo **Receipt** (WH/IN) nếu có Inventory app  
Validate receipt → tăng on-hand

### Delivery (từ SO)
Confirm SO → delivery order  
Validate → giảm on-hand

### Internal transfer
Di chuyển giữa locations; tracked product cập nhật từng location

### Reservation
- At confirmation / Manual / Before scheduled date — ảnh hưởng thời điểm giữ hàng cho SO

### Removal strategy
FIFO / LIFO / FEFO / Closest location / Least packages — quy tắc lấy hàng khi pick

---

## 9. Định giá tồn kho (tóm tắt)

- **Automatic inventory valuation** — bút toán kế toán tự động (cần Accounting)
- **Landed costs** — phân bổ chi phí vận chuyển/thuế vào giá vốn
- **Valuation by lots/serial** — giá theo lô

JustPlay pilot: xác định có bật accounting đầy đủ hay chỉ vận hành kho trước.

---

## 10. Tích hợp chéo

```
Purchase (PO confirm) ──► Receipt ──► Stock
Sales (SO confirm) ──► Delivery ◄── Stock
Reordering (Buy) ──► RFQ/PO ──► Receipt
Reordering (Manufacture) ──► MO ──► Finished goods → Stock
MRP (MO done) ──► Consume components + Produce FG
Maintenance (Block WC) ──► ảnh hưởng lập lịch MO tại work center
```

**Component Status trên MO:** tất cả component phải available mới hoàn thành MO — liên quan multilevel BoM.

---

## 11. Checklist thiết kế JustPlay

### Master data
- [ ] Danh mục SP: Goods tracked vs consumable
- [ ] UoM mua / sản xuất / bán
- [ ] Warehouse & locations (xưởng, kho NVL, kho TP)
- [ ] Routes trên từng nhóm SP (Buy / Manufacture)

### Vận hành kho
- [ ] 1-step hay 2/3-step receipt & delivery?
- [ ] Putaway / removal strategy có cần không?
- [ ] Lot/serial cho TP hay NVL quan trọng?

### Replenishment
- [ ] NVL: Min/Max + vendor lead time
- [ ] BTP/TP: Manufacture route + BoM
- [ ] Có dùng MTO / 0/0/1 cho đơn đặc biệt?

### Báo cáo
- [ ] Forecasted report — planner xem thiếu hàng
- [ ] Stock / Moves history — đối soát

---

## 12. Link doc chi tiết (ưu tiên đọc thêm)

| Chủ đề | URL |
|--------|-----|
| Product type | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/product_management/configure/type.html |
| Routes | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/shipping_receiving/daily_operations/use_routes.html |
| Reordering rules | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html |
| MTO | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/mto.html |
| Warehouses | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/inventory_management/warehouses.html |

---

## 13. Ghi chú pilot `justplay_pilot`

- **25+ sản phẩm** `JP-DEMO-NPL-*` / `JP-DEMO-TP-*` — tồn tại kho chính
- Script: `seed_mrp_demo_data.py` → `seed_stock_demo_data.py` → `seed_odoo_pilot_demo_expand.py`
- **Map đầy đủ:** [pilot-demo-map.md §2](./pilot-demo-map.md#2-sản-phẩm-inventory--mrp)
- Khi mở rộng: Sales → SO → delivery; valuation → [accounting-sales.md](./accounting-sales.md)
