# Thiết kế: Kế hoạch sản xuất (Portal)

> **SoT hiện tại (2026-08):** bảng điều khiển theo **đơn đã xác nhận** tại `/san-xuat/ke-hoach/bang/`.  
> **Đã bỏ UI** Giám sát tiến độ / KHTT / KHCT (URL cũ redirect về board). Model KHTT/KHCT còn trong DB cho NVL / lịch sử.  
> Nguồn khảo sát cũ: [AMIS overall-plan](https://demoamisapp.misa.vn/production/production-plan/overall-plan).

## 0. Luồng Portal mới (MTO phase 1)

```text
ĐĐH xác nhận ──► Hàng đợi kế hoạch SX
                      │ xếp hạng (ưu tiên, hạn, chu kỳ, FIFO)
                      ▼
                 Chuyển xuống SX ──► LSX (gắn sales_order)
                      │
                      ▼
                 Đang SX / Hoàn thành (đồng bộ từ LSX)
```

| Tab | Path | Việc |
|-----|------|------|
| Hàng đợi | `?tab=queue` | Đơn chờ / đã xếp / tạm giữ; ưu tiên; chuyển SX |
| Đã chuyển SX | `?tab=released` | Tiến độ LSX / ETA |
| Lộ trình | `?tab=route` | Timeline KHSX theo đơn (không Chuyển SX) |

Menu: **Kế hoạch sản xuất** + **Tiến độ** (`?tab=released`, phiếu `/ke-hoach/tien-do-don/<id>/`). URL cũ `/ke-hoach/lo-trinh/` redirect về tab Lộ trình.

Menu quyền: `plan_board` (view = xem; update = xếp/giữ; create|update = chuyển SX); `plan_progress` (tiến độ).  
Code: [`services/plan_board.py`](../../san_xuat/services/plan_board.py), view `plan_board`.

**Phase sau:** swimlane MTS/MPS trên cùng board.

---

## 1. Luồng AMIS (benchmark — tham chiếu)

```text
Đơn đặt hàng / Dự báo nhu cầu
        │
        ▼
┌─────────────────────┐
│ Kế hoạch tổng thể   │  KHTT*   OverallPlan
│ (tháng / tuần / quý)│  dòng SP: SL yêu cầu, SL đã lập KH, công suất/ngày
└─────────┬───────────┘
          │ lập từ / tự nhập
          ▼
┌─────────────────────┐
│ Kế hoạch chi tiết   │  KHCT*   DetailProductionPlan
│ (ngày / ca)         │  gắn OverallPlan (optional)
└─────────┬───────────┘
          │ (song song hoặc từ tổng thể)
          ▼
┌─────────────────────┐
│ Kế hoạch NVL        │  KHNVL*  MaterialPlan
│ BOM × SL kế hoạch   │  bucket theo tuần (Col1..ColN) + tồn hiện tại
└─────────┬───────────┘
          │ thiếu hụt
          ▼
┌─────────────────────┐
│ Yêu cầu mua NVL     │  YCM*    MaterialPurchaseRequest
│ (PR nội bộ)         │  có thể gắn SaleOrder / MaterialPlan
└─────────┬───────────┘
          │ duyệt / xử lý mua
          ▼
┌─────────────────────┐
│ Đơn mua hàng        │  DMH*    PurchaseOrder (AMIS)
│ NCC + dòng NVL      │  SL / đã nhận / chưa nhận
└─────────────────────┘
```

**URL AMIS (demo):**

| Màn | Path |
|-----|------|
| Tổng thể | `/production/production-plan/overall-plan` |
| Chi tiết | `/production/production-plan/detail-plan` |
| NVL | `/production/production-plan/materialplan` |
| Yêu cầu mua | `/production/production-plan/materialPurchaseRequest` |
| Đơn mua | `/production/production-plan/purchaseOrder` |

Lịch SX / LSX nằm nhóm **Điều phối** (không thuộc kế hoạch) — Portal giữ stub riêng.

---

## 2. Field AMIS → quyết định Portal

### 2.1 Kế hoạch tổng thể (`OverallPlan`)

| AMIS | Portal |
|------|--------|
| `OverallPlanCode` (KHTT) | `code` auto |
| `OverallPlanName` | `name` |
| `FromDate` / `ToDate` | `date_from` / `date_to` |
| `DetailScheduleBy` (Tuần/Tháng/Quý) | `bucket` = `week` \| `month` \| `quarter` |
| `DataSource` (Dự báo / Đơn ĐH) | `source` = `forecast` \| `sales_order` |
| `OverallPlanStatus` (nháp / …) | `status` = `draft` \| `confirmed` \| `done` \| `cancelled` |
| Organization / Branch | **Bỏ MVP** — JustPlay 1 đơn vị; phase sau map HRM dept |
| Dòng SP: mã, tên, ĐVT, công suất/ngày, SL yêu cầu, SL đã lập KH | `OverallPlanLine` |

**Nguồn dòng SP (Portal):**

- `source=sales_order` → lấy từ **KiotViet đơn** (đã có deep-link `/san-xuat/don-hang/`), snapshot `product_code` + qty còn lại cần SX.
- `source=forecast` → nhập tay / import Excel.

### 2.2 Kế hoạch chi tiết (`DetailProductionPlan`)

| AMIS | Portal |
|------|--------|
| `DetailPlanCode` (KHCT) | `code` |
| Gắn `OverallPlan` (optional) + chế độ *Tự nhập* / *Lập từ tổng thể* | `overall_plan` FK null=True; `origin` |
| `DetailLevel` Ngày / Ca | `grain` = `day` \| `shift` |
| Status | giống tổng thể |
| Dòng: SP × ngày(/ca) × SL | `DetailPlanLine` |

**MVP:** grain = `day` only; ca phase sau.  
**Output:** khi confirm → seed stub **Lệnh sản xuất** (điều phối) — chưa bắt buộc tạo MO thật ở phase 1.

### 2.3 Kế hoạch NVL (`MaterialPlan`)

| AMIS | Portal |
|------|--------|
| `MaterialPlanCode` (KHNVL) | `code` |
| Nguồn: Kế hoạch tổng thể / Đơn ĐH | `source_overall` FK và/hoặc `source_order_codes` |
| Dòng NVL: mã, ĐVT, `RequiredQuantity`, phân bổ `Col1..ColN` (tuần) | `MaterialPlanLine` + `MaterialPlanBucket` |
| `QuantityBalance` (tồn) | đọc `kho_npl.StockBalance` lúc tính / lúc xem |
| `IsCreatedMaterialPurchaseRequest` | flag sau khi sinh PR |

**Công thức nhu cầu (Portal):**

```text
required[material] = Σ (OverallPlanLine.qty_planned × BomLine.qty_with_scrap)
                     cho BomVersion STATUS_ACTIVE của ProductTechDoc(product_code)
shortfall = max(0, required − StockBalance.quantity − on_order_qty)
```

On-order: từ PR/PO Portal (khi có) hoặc 0 ở MVP.

### 2.4 Yêu cầu mua NVL (`MaterialPurchaseRequest`)

| AMIS | Portal |
|------|--------|
| `RequestNumber` (YCM) | `code` |
| Người / đơn vị / hạn / mục đích | `requested_by`, `due_date`, `purpose` |
| `ApproveStatus` / `PurchaseStatus` | `workflow_status`, `purchase_status` |
| Gắn MaterialPlan / SaleOrder | FK `material_plan`, `kv_order_codes` M2M/JSON |
| Dòng NVL | `NplPurchaseRequestLine` → `kho_npl.Material` |

**MVP workflow:** `draft` → `submitted` → `approved` / `rejected` (không clone AMIS Process ID).

### 2.5 Đơn mua hàng (`PurchaseOrder`)

AMIS giữ PO trong app SX; JustPlay **không** SoT mua hàng phức tạp.

| Quyết định | Chi tiết |
|------------|----------|
| MVP | Màn **read-mostly**: list PR đã duyệt + deep-link **phiếu nhập KiotViet** / ghi chú NCC ngoài hệ thống |
| Phase 2 | Model `NplPurchaseOrder` mỏng (NCC text, dòng NVL, SL nhận) → tạo phiếu nhập `kho_npl` |

---

## 3. SoT & biên hệ thống

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| KH tổng thể / chi tiết / NVL / PR | **Portal `san_xuat`** | Mới |
| Đơn bán (nguồn KH) | KiotViet | Snapshot mã + SL vào line |
| BOM định mức | Portal `BomVersion` active | Bắt buộc trước khi tính KH NVL |
| Tồn NPL | Portal `kho_npl` | SoT tồn |
| Đơn mua / nhận hàng TP | KiotViet (tham chiếu) | Không dual-write |
| Mirror Odoo | Không trong phạm vi KH | NPL bridge độc lập |

```text
KV Orders ──► OverallPlanLine (snapshot)
BomVersion ──► MaterialPlanLine (explode)
StockBalance ──► shortfall trên UI / PR
PR approved ──► (phase2) PO / phiếu nhập NPL
DetailPlan confirmed ──► (phase2+) MO điều phối
```

---

## 4. Model đề xuất (`san_xuat`)

```text
OverallPlan
  code, name, date_from, date_to
  bucket: week|month|quarter
  source: forecast|sales_order
  status: draft|confirmed|done|cancelled
  notes, created_by, timestamps

OverallPlanLine
  plan FK, product_code, product_name
  uom_label, qty_required, qty_planned
  capacity_per_day (optional)
  kv_order_id / kv_order_code (nullable)
  sort_order

DetailPlan
  code, name, date_from, date_to
  grain: day|shift
  overall_plan FK null
  origin: from_overall|manual
  status …
DetailPlanLine
  plan FK, product_code, plan_date, shift_code blank
  qty, notes

MaterialPlan
  code, name, date_from, date_to
  overall_plan FK null
  status …
  pr_created bool
MaterialPlanLine
  plan FK, material FK (kho_npl.Material)
  qty_required, qty_on_hand_snapshot, qty_shortfall
MaterialPlanBucket
  line FK, bucket_index, bucket_label, qty

NplPurchaseRequest
  code, request_date, due_date, purpose
  requested_by FK User
  material_plan FK null
  kv_order_codes JSON/text
  workflow_status, purchase_status
NplPurchaseRequestLine
  request FK, material FK, qty, notes
```

Số chứng từ: sequence kiểu `KHTT` / `KHCT` / `KHNVL` / `YCM` (giống prefix AMIS để quen vận hành).

---

## 5. UX Portal (giữ menu hiện có)

Landing `/san-xuat/ke-hoach/` — cập nhật badge khi có model.

| URL | Hành vi MVP |
|-----|-------------|
| `/ke-hoach/tong-the/` | List + tạo/sửa header; tab dòng SP; nút **Lấy từ đơn KV**; confirm |
| `/ke-hoach/chi-tiet/` | List; tạo từ tổng thể (explode theo ngày trong kỳ) hoặc tay |
| `/ke-hoach/npl/` | Tạo từ tổng thể đã confirm → explode BOM; bảng NVL + cột tuần + tồn/thiếu |
| `/ke-hoach/yeu-cau-mua-npl/` | Sinh từ shortfall KH NVL; duyệt đơn giản |
| `/ke-hoach/don-mua-hang/` | Stub enriched: link PR approved + KV phiếu nhập |

**Không làm trong MVP:** nhà máy đa chi nhánh, ca làm việc, AMIS workflow engine, PO đầy đủ NCC, công suất chuyền.

---

## 6. Thứ tự implement

| Phase | Scope | Done khi |
|-------|--------|----------|
| **P0** | Models + admin + list/detail CRUD tổng thể + dòng SP (manual) | Tạo `KHTT`, sửa dòng, status draft→confirmed |
| **P1** | Import dòng từ đơn KV (chọn đơn / còn SX) | 1 đơn KV → nhiều `OverallPlanLine` |
| **P2** | MaterialPlan từ OverallPlan + BOM active + tồn `kho_npl` | Bảng nhu cầu + shortfall đúng vài mã pilot |
| **P3** | NplPurchaseRequest từ shortfall + duyệt | PR → approved |
| **P4** | DetailPlan từ OverallPlan (theo ngày) | List KHCT; link điều phối stub |
| **P5** | PO mỏng / phiếu nhập NPL | Optional |

Pilot gợi ý: mã TP đã có hồ sơ BOM (vd. `SP008073`) + NPL đã sync.

---

## 7. API / service nội bộ

```text
san_xuat/services/planning.py
  build_overall_lines_from_kv_orders(order_ids) -> list[line vals]
  explode_material_plan(overall_plan_id) -> MaterialPlan + lines + buckets
  build_pr_from_material_plan(material_plan_id, only_shortfall=True)
  explode_detail_days(overall_plan_id) -> DetailPlan + lines
```

CLI (optional): `python manage.py san_xuat_plan_explode --overall KHTT00001 --apply`

---

## 8. Quyền

Giữ keys đã seed: `plan`, `plan_overall`, `plan_detail`, `plan_npl`, `npl_pr`, `purchase_order`.  
Thêm action khi cần: `plan_confirm`, `npl_pr_approve` (hoặc dùng `edit` chung MVP).

---

## 9. Khác biệt có chủ đích so với AMIS

1. **Một SoT Portal** — không sync kế hoạch sang AMIS/Odoo.
2. **TP từ KV, NPL từ `kho_npl`** — không danh mục VTHH gộp.
3. **BOM Portal** bắt buộc trước KH NVL — không soft-create item trong form KH.
4. **Đơn mua** mỏng hơn AMIS; ưu tiên nối kho NPL / KV nhập.
5. **Không nhà máy đa OU** ở MVP.

---

## 10. Tiêu chí xong (MVP = P0–P3)

- [ ] Tạo / confirm kế hoạch tổng thể có dòng SP.
- [ ] Lấy được ít nhất 1 đơn KV vào dòng KH.
- [ ] Explode KH NVL từ BOM active; số khớp tay ± làm tròn.
- [ ] Shortfall phản ánh tồn `kho_npl`.
- [ ] Sinh PR từ shortfall và duyệt được.
- [ ] Menu hub không còn stub trống cho 4 màn đầu (đơn mua có thể vẫn tham chiếu KV).
