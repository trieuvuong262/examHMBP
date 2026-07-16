# Thiết kế: Giá thành kế hoạch (Portal)

> Nguồn khảo sát: AMIS Sản xuất demo — tenant **Công ty Cổ phần may** (2026-07-16).  
> Base path: `/production/plan-cost/*`.  
> Menu Portal scaffold: [`hub-portal.md`](./hub-portal.md) § Giá thành kế hoạch.  
> Engine đã có: `san_xuat.services.costing.compute_costing` + `CostingSnapshot` trong Hồ sơ SX.

## 1. IA AMIS (benchmark)

```text
Giá thành kế hoạch
├── GT định mức sản phẩm      /plan-cost/product-standard-cost    ProductStandardCost
├── GTKH theo đơn đặt hàng    /plan-cost/sale-order-plan-cost     SaleOrderPlanCost
└── Thuê gia công             (ngoài phạm vi hub giá thành Portal)
```

Portal landing (`hub_costing.html`) **đã khớp 2 mục đầu** — giữ URL:

| Portal | AMIS |
|--------|------|
| `/gia-thanh/dinh-muc/` | GT định mức sản phẩm |
| `/gia-thanh/theo-don/` | GTKH theo đơn đặt hàng |

---

## 2. Luồng AMIS → Portal

```text
BOM active + ProcessStep + giá NPL (kho_npl)
        │  compute_costing()  [đã có]
        ▼
┌──────────────────────────┐
│ Hồ sơ SX / tab Costing   │  SoT chi tiết 1 SP (live + snapshot)
└────────────┬─────────────┘
             │ xuất / chốt vào bảng kỳ
             ▼
┌──────────────────────────┐
│ Bảng GT định mức (GTDM)  │  nhiều SP × kỳ; nguồn Theo BOM | Tự nhập
└────────────┬─────────────┘
             │ × SL đơn KV + chi phí thêm (optional)
             ▼
┌──────────────────────────┐
│ Bảng GTKH theo đơn (GTĐH)│  đơn × dòng SP → tổng giá thành kế hoạch
└──────────────────────────┘
```

AMIS wizard:

1. **Định mức:** Kỳ + tên bảng → chọn SP/BOM (Theo BOM | Tự nhập) → tính NVL trực tiếp → tính GT SP.  
2. **Theo đơn:** Kỳ + tên bảng → lấy nhanh đơn ĐH → tính GT đơn (= định mức × SL + cột chi phí cấu hình).

---

## 3. Field AMIS → quyết định Portal

### 3.1 GT định mức sản phẩm (`ProductStandardCost`)

| AMIS | Portal |
|------|--------|
| Bảng: `FromDate`–`ToDate`, `ProductStandardCostName`, `Status` | `StandardCostSheet` |
| Nguồn tính: Theo BOM / Tự nhập | `source`: `from_bom` \| `manual` |
| Dòng: mã SP, ĐVT, BOM, … | `StandardCostLine` |
| Thành phần chi phí (cột động AMIS) | **MVP cố định:** NVL + nhân công + phụ phí (+ `extra_cost` optional) — map `compute_costing` |
| Nhà máy | **Bỏ MVP** |

**SoT chi tiết:** vẫn Hồ sơ SX. Bảng GTDM là **bản chốt / tập hợp theo kỳ** để báo cáo và làm đầu vào GTKH theo đơn — không thay tab Costing.

Khi `source=from_bom`:

```text
line.unit_cost = compute_costing(bom_active).total_cost
line.material_cost / labor_cost / overhead_cost = tương ứng
line.bom_version FK, snapshot optional → CostingSnapshot
```

Khi `source=manual`: user nhập `unit_cost` (và optionally 3 thành phần).

### 3.2 GTKH theo đơn (`SaleOrderPlanCost`)

| AMIS | Portal |
|------|--------|
| Bảng: kỳ, tên, `PlanCost` tổng, status | `OrderPlanCostSheet` |
| Dòng đơn: số ĐH, KH, hạn SX | snapshot từ **KiotViet** |
| Dòng SP: mã, SL, GT định mức (ĐVT), chi phí SX, … | `OrderPlanCostLine` |
| Cột động (vận chuyển, lưu kho, …) | MVP: `extra_cost` trên dòng/đơn; phase sau bảng `CostExtraItem` |

```text
line.plan_cost = line.qty × standard_unit_cost + line.extra_cost
sheet.total_plan_cost = Σ line.plan_cost
```

`standard_unit_cost` lấy từ:

1. `StandardCostLine` của bảng GTDM đã **confirmed** (cùng SP, kỳ giao nhau), hoặc  
2. Fallback: `compute_costing(bom_active).total_cost` / snapshot mới nhất.

### 3.3 Thuê gia công

AMIS có menu riêng cạnh giá thành. **Portal:** không đưa vào hub `/gia-thanh/`; nếu cần sau → stub điều phối / module riêng.

---

## 4. SoT & biên

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| Định mức NVL + NC 1 SP | Hồ sơ `BomVersion` + `compute_costing` | Đã có |
| Chốt costing 1 SP | `CostingSnapshot` | Đã có |
| Bảng GT định mức theo kỳ | Portal `StandardCostSheet` | Mới — tổng hợp |
| Bảng GTKH theo đơn | Portal `OrderPlanCostSheet` | Mới |
| Đơn / giá bán | KiotViet | Snapshot mã, SL, giá |
| Giá NPL | `kho_npl` avg | Qua `material_avg_price` |
| Odoo / AMIS | Không sync giá thành | |

---

## 5. Model đề xuất

```text
StandardCostSheet
  name, date_from, date_to
  source: from_bom|manual
  status: draft|confirmed|cancelled
  notes, created_by, timestamps

StandardCostLine
  sheet FK
  product_code, product_name, uom_label
  bom_version FK null
  material_cost, labor_cost, overhead_cost, unit_cost
  costing_snapshot FK null
  sort_order

OrderPlanCostSheet
  name, date_from, date_to
  standard_sheet FK null   # ưu tiên lấy đơn giá từ bảng này
  status: draft|confirmed|cancelled
  total_plan_cost
  notes, created_by, timestamps

OrderPlanCostLine
  sheet FK
  kv_order_code, kv_order_id null
  customer_name, order_date, due_date
  product_code, product_name, uom_label
  qty
  unit_standard_cost      # snapshot lúc tính
  extra_cost              # vận chuyển / khác (MVP 1 số)
  line_plan_cost          # qty * unit_standard_cost + extra_cost
  sort_order
```

Không clone engine cột động `ColumnCostItemCustom` AMIS ở MVP.

---

## 6. UX Portal

| URL | Hành vi |
|-----|---------|
| `/gia-thanh/` | Landing 2 mục + link Hồ sơ Costing (đã có) |
| `/gia-thanh/dinh-muc/` | List bảng GTDM; tạo wizard ngắn: kỳ → chọn SP có BOM active → tính → confirm |
| `/gia-thanh/theo-don/` | List bảng GTĐH; tạo: kỳ → chọn đơn KV trong kỳ → lấy GTDM → tính tổng |
| `/san-xuat/ho-so/…?tab=costing` | SoT chi tiết (giữ) — deep-link từ dòng GTDM |

**Không stub trống:** màn định mức MVP có thể **redirect/list** các `CostingSnapshot` + nút “Tạo bảng kỳ” nếu chưa làm full sheet — nhưng mục tiêu là sheet thật (C0–C1).

---

## 7. Thứ tự implement

| Phase | Scope | Done khi |
|-------|--------|----------|
| **C0** | List GTDM = SP có BOM active + live `compute_costing` (không sheet) | Thay stub bằng bảng đọc được; link Hồ sơ |
| **C1** | `StandardCostSheet` + lines từ BOM; confirm | Chốt bảng kỳ |
| **C2** | `OrderPlanCostSheet` + lines từ đơn KV × unit_cost GTDM/fallback | Có tổng GTKH theo đơn |
| **C3** | `extra_cost` trên dòng đơn; export Excel | Chi phí thêm + xuất báo cáo |
| **C4** | (Optional) cấu hình loại chi phí thêm | Gần AMIS cost columns |

C0 tận dụng code sẵn — ship nhanh. C1–C2 mới là “bảng” kiểu AMIS.

---

## 8. Service

```text
san_xuat/services/plan_costing.py
  build_standard_sheet_from_bom(sheet, product_codes) -> lines  # dùng compute_costing
  confirm_standard_sheet(sheet_id)
  build_order_sheet_from_kv(sheet, order_ids, standard_sheet_id=None) -> lines
  resolve_unit_standard_cost(product_code, *, standard_sheet=None) -> Decimal
```

Reuse: `compute_costing`, `save_costing_snapshot`, KV order lookup (module `kiotviet`).

---

## 9. Quyền

Giữ `costing_norm`, `costing_by_order` (và nhóm `costing` nếu đã seed).  
Confirm sheet: dùng `edit` hoặc thêm `costing_confirm` sau.

---

## 10. Khác biệt có chủ đích so với AMIS

1. **Hồ sơ SX = SoT định mức chi tiết**; AMIS “bảng định mức” = lớp tổng hợp theo kỳ trên Portal.  
2. **Không engine cột chi phí động** — NVL/NC/phụ phí (+ extra đơn giản).  
3. **Đơn từ KiotViet**, không SO AMIS.  
4. **Thuê gia công** không nằm trong hub giá thành.  
5. Giá NPL lấy `kho_npl`, không kho AMIS.

---

## 11. Tiêu chí xong (MVP = C0–C2)

- [ ] `/gia-thanh/dinh-muc/` hiện được GT/SP từ BOM active (C0) hoặc bảng đã chốt (C1).  
- [ ] Tạo/confirm `StandardCostSheet` cho ≥1 mã pilot (`SP008073`).  
- [ ] Tạo `OrderPlanCostSheet` từ ≥1 đơn KV; `line_plan_cost ≈ qty × unit_cost`.  
- [ ] Landing không còn “Sắp làm” trống cho 2 mục chính; vẫn link Hồ sơ Costing.
