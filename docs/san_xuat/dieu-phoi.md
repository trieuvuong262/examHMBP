# Thiết kế: Điều phối & thực thi (Portal)

> Nguồn khảo sát: AMIS Sản xuất demo — tenant **Công ty Cổ phần may** (2026-07-16).  
> Paths: `/production/production-execution/*`.  
> Menu Portal scaffold: [`hub-portal.md`](./hub-portal.md) § Điều phối.  
> Upstream: [`ke-hoach-san-xuat.md`](./ke-hoach-san-xuat.md).

## 1. Menu AMIS (benchmark)

```text
Điều phối và thực thi
├── Lệnh sản xuất              /order                 LSX*   ProductionOrder
├── Lệnh tháo dỡ               /dismantle-order       LTD*   DismantleOrder
├── Lịch sản xuất              /schedule                     ProductionSchedule
├── Yêu cầu xuất vật tư        /material-request      YCXK*  MaterialRequest
├── Thống kê sản xuất          /statistics            TKSX*  Statistics
├── Yêu cầu nhập thành phẩm    /product-request       YCNTP* MaterialInRequest
├── Bàn giao bán thành phẩm    /handover              BG*    Handover
└── Tình hình bàn giao sản xuất  (cùng nhóm handover / filter trạng thái)
```

**Không nằm trong submenu Điều phối AMIS** (Portal đang có stub riêng):

| Portal stub | Ghi chú AMIS |
|-------------|--------------|
| NPL thừa | Không thấy menu riêng; có thể gộp kho / sau tháo dỡ |
| Trả lại BTP | Không thấy URL riêng; bàn giao có trạng thái Từ chối |

**Liên quan ngoài nhóm** (không thiết kế trong doc này): Giao việc, QC, Đóng gói, Kho vật tư AMIS.

---

## 2. Luồng thực thi AMIS → Portal

```text
KH chi tiết / Đơn KV / thủ công
        │
        ▼
┌──────────────────┐
│ Lệnh sản xuất    │  product_code, qty, hạn, BOM, quy trình (công đoạn)
│ (LSX)             │  trạng thái: chưa / đang / xong / hủy
└────────┬─────────┘
         │ BOM explode
         ▼
┌──────────────────┐     duyệt      ┌─────────────────┐
│ YC xuất vật tư   │ ─────────────► │ Phiếu xuất NPL  │  SoT: kho_npl.StockIssue
│ (YCX)            │                └─────────────────┘
└────────┬─────────┘
         │ (optional) lịch / tổ
         ▼
┌──────────────────┐
│ Thống kê SX      │  SL đạt / lỗi theo ngày (+ công đoạn nếu có)
│ (TKSX)           │
└────────┬─────────┘
         ├──────────────────────┐
         ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│ Bàn giao BTP     │   │ YC nhập TP       │
│ (công đoạn A→B)  │   │ (YCNTP)          │
└──────────────────┘   └────────┬─────────┘
                                │
                                ▼
                       Hồ sơ / ghi nhận TP
                       (KV phiếu nhập — phase sau)
```

---

## 3. Field AMIS → quyết định Portal

### 3.1 Lệnh sản xuất (`ProductionOrder` / LSX)

| AMIS | Portal |
|------|--------|
| `OrderNumber` | `code` (LSX) |
| `OrderDate`, `DeliveryDate`, start/end | `order_date`, `due_date`, `planned_start`, `planned_end` |
| `OrderStatus` (chưa / đang / …) | `status`: `draft` \| `released` \| `in_progress` \| `done` \| `cancelled` |
| `OrderPriority` | `priority` 1–5 |
| `InventoryItemCode/Name`, `TotalQuantity`, produced/pass/remain/defect | dòng / header: `product_code`, `qty`, counters |
| `MaterialStatus` | derived từ YCX + phiếu xuất |
| `OverallPlanID` / `PlanID` / `SaleOrderID` | FK `detail_plan` null, `overall_plan` null, `kv_order_code` |
| `BillOfMaterials` + `ProductionProcess` | `bom_version` FK (`BomVersion` active); công đoạn = `ProcessStep` |
| Tổ / nhà máy | `team_label` text MVP (không multi-OU) |
| Gửi kế toán | **Bỏ** |

**Nguồn tạo LSX (MVP):** thủ công theo `product_code` + BOM active; **P1:** từ `DetailPlan` / đơn KV.

### 3.2 Lịch sản xuất (`ProductionSchedule`)

AMIS: lưới tuần theo đơn vị + danh sách lịch (tên, từ–đến, trạng thái).

| Quyết định Portal |
|-------------------|
| **MVP:** view lịch (calendar/week) đọc từ LSX `planned_start`/`due_date` — **không** model lịch riêng |
| **Phase sau:** `ProductionSchedule` gán tổ/ngày nếu cần kéo-thả |

### 3.3 Yêu cầu xuất vật tư (`MaterialRequest` / YCXK)

| AMIS | Portal |
|------|--------|
| `MaterialRequestNo` | `code` (YCX) |
| Gắn LSX / LTD | FK `production_order` (và sau: `disassembly_order`) |
| Dòng NVL: qty yêu cầu / đã xuất | `MaterialIssueRequestLine` → `kho_npl.Material` |
| Sync kho AMIS | **Portal:** duyệt → tạo / gắn `kho_npl.StockIssue` |

### 3.4 Thống kê sản xuất (`Statistics` / TKSX)

| AMIS | Portal |
|------|--------|
| `StatisticsCode`, ngày, LSX, SP, công đoạn | `ProductionStat` + lines |
| `ProducedQuantity`, flags QC / YC nhập / bàn giao | `qty_good`, `qty_defect`; flags derived |
| Tổ / người thống kê | `reported_by`, `team_label` |

Cập nhật counters trên LSX khi confirm phiếu thống kê.

### 3.5 Yêu cầu nhập thành phẩm (`MaterialInRequest` / YCNTP)

| AMIS | Portal |
|------|--------|
| Lập từ phiếu thống kê / LSX | FK `production_order`, optional `stat` |
| Sync kho TP AMIS | **Portal MVP:** chứng từ nội bộ + deep-link KV tồn/phiếu nhập; **không** auto-ghi KV |
| Phase sau | Hook tạo phiếu nhập KV nếu API cho phép |

### 3.6 Bàn giao BTP (`Handover` / BG)

| AMIS | Portal |
|------|--------|
| Từ công đoạn → công đoạn, SL gửi/nhận, xác nhận/từ chối | `WipHandover` |
| Scope cùng LSX / khác LSX | `scope`: `same_order` \| `cross_order` |
| Tình hình bàn giao | List filter status (không cần model riêng) |

Phụ thuộc `ProcessStep` trên BOM — nếu SP chỉ 1 công đoạn, bàn giao **optional**.

### 3.7 Lệnh tháo dỡ (`DismantleOrder` / LTD)

| AMIS | Portal |
|------|--------|
| SP tháo + TP/NVL thu hồi + BOM tháo dỡ | Phase sau — cần định mức tháo dỡ (đã nêu ở khảo sát SP/NVL) |
| MVP | Giữ stub + link kho NPL |

### 3.8 NPL thừa / Trả lại BTP (stub Portal)

| Mục | Quyết định |
|-----|------------|
| NPL thừa | Phase sau: phiếu điều chỉnh / nhập lại `kho_npl` gắn LSX |
| Trả lại BTP | Gộp vào bàn giao (`rejected` / phiếu reverse) — **không** menu riêng MVP |

---

## 4. SoT & biên hệ thống

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| LSX, YCX, TKSX, YCNTP, bàn giao | Portal `san_xuat` | Mới |
| Xuất NPL thật | `kho_npl.StockIssue` | YCX duyệt → phiếu xuất |
| Tồn NPL | `kho_npl.StockBalance` | Kiểm tra khi duyệt YCX |
| BOM / công đoạn | `BomVersion` + `ProcessStep` | Bắt buộc trước release LSX |
| Đơn / tồn TP | KiotViet | Snapshot mã SP; nhập TP không SoT Portal |
| Odoo | Không trong điều phối | Mirror NPL độc lập |

```text
LSX ──explode BOM──► YCX ──approve──► StockIssue (kho_npl)
LSX ◄──counters── TKSX
TKSX ──► YCNTP (chứng từ) ──link──► KV (tham chiếu)
TKSX ──► WipHandover (nếu đa công đoạn)
```

---

## 5. Model đề xuất (`san_xuat`)

```text
ProductionOrder
  code, order_date, due_date, planned_start, planned_end
  product_code, product_name, qty
  qty_produced, qty_good, qty_defect   # cập nhật từ TKSX
  status, priority
  bom_version FK
  detail_plan FK null, overall_plan FK null
  kv_order_code, team_label, notes
  created_by, timestamps

MaterialIssueRequest
  code, request_date, status: draft|submitted|approved|done|cancelled
  production_order FK
  requested_by, notes
  stock_issue FK null   # kho_npl.StockIssue khi đã xuất
MaterialIssueRequestLine
  request FK, material FK, qty_requested, qty_issued

ProductionStat
  code, stat_date, production_order FK
  process_step FK null   # hoặc stage_name text
  qty_good, qty_defect, reported_by, notes
  status: draft|confirmed

FgReceiptRequest
  code, request_date, production_order FK
  stat FK null
  qty, status: draft|submitted|done|cancelled
  kv_receipt_ref  # text / id tham chiếu

WipHandover
  code, production_order FK
  from_step FK, to_step FK
  qty_sent, qty_received
  sent_by, received_by, sent_at, received_at
  status: draft|sent|confirmed|rejected
  notes
```

Prefix gợi ý: `LSX`, `YCX`, `TKSX`, `YCNTP`, `BG` (quen AMIS).

---

## 6. UX Portal (giữ URL hiện có)

| URL | Hành vi |
|-----|---------|
| `/dieu-phoi/` | Landing + KPI: LSX đang chạy, YCX chờ duyệt, TKSX hôm nay |
| `/dieu-phoi/lenh-sx/` | List + CRUD; release; tabs: NVL (BOM), tiến độ, chứng từ liên quan |
| `/dieu-phoi/lich-sx/` | Calendar/week view từ LSX (read-only MVP) |
| `/dieu-phoi/yeu-cau-xuat-vt/` | List YCX; tạo từ LSX; duyệt → `StockIssue` |
| `/dieu-phoi/thong-ke-sx/` | Nhập SL; confirm → cập nhật LSX |
| `/dieu-phoi/yeu-cau-nhap-tp/` | Tạo từ TKSX/LSX; link KV |
| `/dieu-phoi/ban-giao-btp/` | Handover đa công đoạn |
| `/dieu-phoi/tinh-hinh-ban-giao/` | Filter/dashboard handover (cùng model) |
| `/dieu-phoi/lenh-thao-do/` | Stub → phase sau |
| `/dieu-phoi/npl-thua/` | Stub → phase sau / deep-link kho |
| `/dieu-phoi/tra-lai-btp/` | Redirect hoặc filter `rejected` handover |

---

## 7. Thứ tự implement

| Phase | Scope | Done khi |
|-------|--------|----------|
| **D0** | `ProductionOrder` CRUD + gắn BOM active + status | Tạo/release LSX pilot (`SP008073`) |
| **D1** | `MaterialIssueRequest` từ BOM × qty; duyệt → `StockIssue` | Xuất NPL thật trên Portal |
| **D2** | `ProductionStat` + cập nhật counters LSX | Ghi SL đạt/lỗi |
| **D3** | `FgReceiptRequest` + link KV | Chứng từ YCNTP |
| **D4** | Lịch read-only từ LSX | Week view |
| **D5** | `WipHandover` (nếu BOM ≥ 2 `ProcessStep`) | Gửi/nhận BTP |
| **D6** | Tháo dỡ + NPL thừa | Sau có định mức tháo dỡ |

Phụ thuộc kế hoạch: D0 có thể chạy **song song** KH; tạo LSX từ `DetailPlan` khi P4 kế hoạch xong.

---

## 8. Service nội bộ

```text
san_xuat/services/dispatch.py
  create_mo_from_bom(product_code, qty, **refs) -> ProductionOrder
  build_material_issue_request(mo_id) -> MaterialIssueRequest  # explode BomLine
  approve_material_issue(request_id, user) -> StockIssue
  confirm_stat(stat_id) -> update MO counters
  create_fg_receipt_from_stat(stat_id) -> FgReceiptRequest
```

---

## 9. Quyền

Giữ keys: `dispatch`, `mo`, `disassembly`, `schedule`, `material_issue_req`, `prod_stats`, `fg_receipt_req`, `npl_surplus`, `wip_handover`, `wip_return`, `handover_status`.

MVP thêm hành động: `mo_release`, `material_issue_approve` (hoặc dùng `edit`).

---

## 10. Khác biệt có chủ đích so với AMIS

1. **Xuất NPL SoT Portal** — không sync sang AMIS Kho; YCX là lớp điều phối trước `StockIssue`.
2. **TP qua KV** — YCNTP không dual-write kho TP AMIS/Odoo.
3. **Lịch mỏng** — view trên LSX, không engine xếp lịch đầy đủ.
4. **Bàn giao optional** — chỉ khi có nhiều `ProcessStep`.
5. **Giao việc / QC / Đóng gói AMIS** — ngoài phạm vi điều phối MVP (hub QC riêng vẫn stub).
6. **Thu gọn menu:** Trả lại BTP / NPL thừa không ưu tiên model riêng.

---

## 11. Tiêu chí xong (MVP = D0–D3)

- [ ] Tạo / release LSX gắn BOM active.
- [ ] Sinh YCX từ BOM; duyệt tạo phiếu xuất `kho_npl`.
- [ ] TKSX cập nhật SL trên LSX.
- [ ] YCNTP tạo được và có lối tắt xem kho/phiếu KV.
- [ ] Landing điều phối hiện số LSX đang chạy / YCX chờ duyệt.
