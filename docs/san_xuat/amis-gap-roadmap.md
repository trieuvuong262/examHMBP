# Khảo sát AMIS Sản xuất → Gap Portal & lộ trình làm tiếp

> Nguồn benchmark: [AMIS Sản xuất demo](https://demoamisapp.misa.vn/) — tenant **Công ty Cổ phần May ABC** (khảo sát 2026-07-16).  
> So sánh với hub Portal: `/san-xuat/` — thiết kế menu: [`hub-portal.md`](./hub-portal.md).

---

## 1. Tóm tắt nhanh

| Trạng thái | Ý nghĩa |
|------------|---------|
| **Đã có thật** | CRUD + workflow + (nơi cần) nối `kho_npl` / KiotViet — pilot E2E đã chạy |
| **MVP mỏng** | Có màn + model, còn thiếu depth AMIS (engine kho GC, dừng máy, …) |
| **Chưa làm** | Chưa có menu / nghiệp vụ tương ứng |

**Kết luận chung (cập nhật 2026-07-17):** Portal **đã vận hành được một vòng SX thật** (KHTT → LSX → xuất NPL → TKSX → QC → YCNTP/KV → đóng gói → truy xuất). Checklist GĐ1–3 đã tick. Còn lại chủ yếu là **làm dày UX/AMIS parity** và vài gap vận hành (trả BTP, BOM tháo/NVL thay thế, dashboard extras).

**SoT Portal (giữ nguyên):**

| Dữ liệu | SoT |
|---------|-----|
| NPL nhập/xuất/kiểm kê | `kho_npl` |
| Đơn / tồn TP | KiotViet |
| BOM / costing chi tiết | Hồ sơ SX (`san_xuat`) |
| Kế hoạch / LSX / QC / GT kế hoạch | Portal hub (không sync AMIS/Odoo) |

---

## 2. So sánh menu AMIS ↔ Portal

| AMIS Sản xuất | Portal | Trạng thái |
|---------------|--------|------------|
| **Tổng quan** | `/san-xuat/tong-quan/` | ✅ KPI + chart + Top 10 + dừng chuyền + lệnh theo TT (kiểu AMIS) |
| **Đơn đặt hàng** | `/san-xuat/don-hang/` | ✅ SoT Portal — [`don-dat-hang.md`](./don-dat-hang.md) |
| **Kế hoạch SX** (5 mục) | KHTT / KHCT / KHNVL / YCM / DMH | ✅ P0–P5 CRUD + workflow |
| **Điều phối** | LSX, YCX, TKSX, YCNTP, lịch, BTP, tháo dỡ, NPL thừa… | ✅ D0–D6 — trả BTP còn mỏng |
| **Giao việc** | `/san-xuat/giao-viec/` (+ `tasks`) | ✅ Gắn LSX / tổ / WorkTask |
| **Kiểm tra CL** | YCKT, PKT, danh mục, cảnh báo, sidebar “Tiêu chuẩn” | ✅ Q0–Q5 |
| **Đóng gói** | `/san-xuat/dong-goi/` | ✅ Dòng size/SKU, YCNTP, lô |
| **Kho vật tư** | **Kho NPL** (`kho_npl`) | ✅ SoT NPL |
| **Truy xuất nguồn gốc** | `/san-xuat/truy-xuat/` | ✅ Timeline + tra LSX/YCX/KV/lô NPL/ĐG |
| **Giá thành KH** | `/san-xuat/gia-thanh/` | ✅ C0–C4 (định mức, theo đơn, extra, loại CP) |
| **Thuê gia công** | `/san-xuat/thue-gia-cong/` | ✅ Sổ tay xuất/nhận NVL-BTP — **chưa** trừ/cộng `kho_npl` tự động |
| **Báo cáo vận hành** | `/san-xuat/bao-cao-van-hanh/` | ✅ KPI + lọc + CSV + chart (khác module `reports` NV) |
| **Sản phẩm, NVL** | `/san-xuat/san-pham-nvl/` | ✅ Landing — catalog vẫn phân tán KV + `kho_npl` + Hồ sơ |
| **Quy trình** | `/san-xuat/quy-trinh/` | ⚠️ Chủ yếu read-only từ `ProcessStep` |
| **Năng lực SX** | `/san-xuat/nang-luc/` | ✅ Catalog tổ/chuyền + tải kỳ |
| **Danh mục khác** | — | ❌ ĐVT / nhóm SP / lý do dừng máy… |
| *(Portal thêm)* | **Hồ sơ SX / BOM / Costing** | ✅ Điểm mạnh |

**Tham chiếu thiết kế chi tiết:**

- Kế hoạch: [`ke-hoach-san-xuat.md`](./ke-hoach-san-xuat.md)
- Điều phối: [`dieu-phoi.md`](./dieu-phoi.md)
- QC: [`kiem-tra-chat-luong.md`](./kiem-tra-chat-luong.md)
- Giá thành: [`gia-thanh-ke-hoach.md`](./gia-thanh-ke-hoach.md)

---

## 3. Dashboard tổng quan — đã có / còn thiếu

**Đã có trên Portal** (`services/overview.py` + `hub_overview.html`):

- Filter kỳ (tháng / từ–đến) + mã sản phẩm + tổ/đơn vị SX
- KPI lệnh sản xuất / sản lượng / lỗi / cảnh báo chất lượng
- Chart: trạng thái lệnh · sản lượng theo ngày · kết quả kiểm tra
- Top 10 sản phẩm sản lượng / lỗi cao
- Lý do dừng chuyền (% phút) + lệnh theo trạng thái trong kỳ
- Cảnh báo chất lượng mở + lối tắt hub

**So với [AMIS demo](https://demoamisapp.misa.vn/):** đã phủ các widget chính; còn có thể làm dày filter nhóm SP / đa nhà máy nếu pilot yêu cầu.

---

## 4. Phạm vi đã implement (trước đây là “scaffold”)

> Mục này giữ bảng acceptance gốc để đối chiếu; cột **TT** phản ánh code hiện tại.

### 4.1 Kế hoạch (P0–P5)

| Phase | Scope | TT |
|-------|--------|----|
| **P0** | CRUD KHTT + dòng SP | ✅ |
| **P1** | Import dòng từ đơn KV | ✅ |
| **P2** | KH NVL từ BOM + tồn `kho_npl` + shortfall | ✅ |
| **P3** | YCM từ shortfall + duyệt | ✅ |
| **P4** | KHCT theo ngày | ✅ |
| **P5** | PO mỏng / link phiếu nhập | ✅ |

### 4.2 Điều phối (D0–D6)

| Phase | Scope | TT |
|-------|--------|----|
| **D0** | LSX CRUD + BOM + release | ✅ |
| **D1** | YCX → `StockIssue` (+ lô) | ✅ *(bug link `stock_issue` khi có đính kèm đã sửa)* |
| **D2** | TKSX + counters LSX | ✅ |
| **D3** | YCNTP + link KV | ✅ *(pilot: `YCNTP-2026-0002` ← `PN002960`)* |
| **D4** | Lịch read-only | ✅ |
| **D5** | Bàn giao BTP | ✅ tạo/nhận — **trả BTP còn mỏng** |
| **D6** | Tháo dỡ + NPL thừa | ✅ |

### 4.3 Kiểm tra chất lượng (Q0–Q5)

| Phase | Scope | TT |
|-------|--------|----|
| **Q0–Q3** | Danh mục + YCKT + PKT + dòng TC/lỗi | ✅ |
| **Q4** | Nối TKSX → YCKT / cảnh báo lỗi | ✅ |
| **Q5** | Sidebar “Tiêu chuẩn” + landing | ✅ |

### 4.4 Giá thành kế hoạch (C0–C4)

| Phase | Scope | TT |
|-------|--------|----|
| **C0–C4** | Live BOM, định mức, theo đơn KV, extra + Excel, loại CP | ✅ |

---

## 5. Backlog vận hành nhà máy (cập nhật 2026-07-17)

### 5.1 Ưu tiên cao — đã làm

| Gap | Đã làm |
|-----|--------|
| **Quy trình công đoạn sống** | Hồ sơ sản xuất → tab Quy trình: chuẩn phút/cái, đơn giá sản phẩm, gắn tổ/máy (`ProcessStep`) |
| **Giá thành thực tế / chốt kỳ** | `/san-xuat/gia-thanh/thuc-te/` — nguyên vật liệu đã xuất + lương sản phẩm + phí gia công; chốt kỳ; lối vào từ lệnh sản xuất |
| **Xử lý hàng không đạt** | Từ cảnh báo chất lượng → tạo phiếu (sửa hàng / phế / tái sản xuất / chấp nhận dùng) → `/san-xuat/ncr/` |
| **Giữ chỗ tồn** | `StockReservation`; xác nhận kế hoạch nguyên phụ liệu + tạo yêu cầu xuất → giữ chỗ; thiếu hụt theo tồn khả dụng; xuất xong → đã tiêu thụ |
| **Xác nhận tại xưởng** | `/san-xuat/shop-floor/` — quét/nhập mã lệnh sản xuất hoặc thống kê sản xuất → xác nhận công đoạn nhanh |

### 5.2 Ưu tiên trung bình — đã làm (MVP)

| Gap | Đã làm |
|-----|--------|
| **Lệnh sản xuất mẫu** | Cờ “lệnh sản xuất mẫu” khi tạo; nhãn trên chi tiết lệnh |
| **Dừng chuyền / hiệu suất thiết bị** | `/san-xuat/dung-chuyen/` — ghi dừng + tỷ lệ sẵn sàng thô theo tổ |
| **Lương sản phẩm → nhân sự** | Nút xuất CSV nhân sự trên trang lương sản phẩm |
| **Danh mục thống nhất** | `/san-xuat/catalog/` — nhóm sản phẩm + hồ sơ + nguyên phụ liệu + đơn vị tính |
| **Vùng chờ / đa vị trí** | Loại vị trí kho + `/san-xuat/staging/` (gán loại + xem giữ chỗ) |

### 5.3 Đã làm trước (ops_depth / GĐ3)

| Hạng mục | Ghi chú |
|----------|---------|
| **Trả lại bán thành phẩm** | CRUD + xác nhận; gắn bàn giao đã xác nhận; đảo công đoạn |
| **BOM tháo / nguyên vật liệu thay thế** | Lệnh tháo dỡ “Đổ từ BOM”; `BomLine.substitute_material` → yêu cầu xuất |
| **Cân đối năng lực ↔ kế hoạch chi tiết** | Cảnh báo vượt năng lực; gán tổ vào dòng kế hoạch chi tiết |
| **Thống kê / kiểm tra theo size** | Trường size/mã phân loại/màu; yêu cầu kiểm tra kế thừa từ thống kê sản xuất |
| **Dashboard bổ sung** | Top sản phẩm + dừng chuyền + lệnh theo trạng thái trong kỳ |
| **Lịch sản xuất chỉnh được** | Đổi ngày/tổ trên lịch tuần |
| **Thuê gia công → kho** | Best-effort phiếu xuất khi gửi / điều chỉnh khi nhận |
| **Lương sản phẩm** | Đơn giá công đoạn × thống kê đã xác nhận → `/san-xuat/luong-san-pham/` |
| **Hàng về dự kiến trong thiếu hụt** | Số lượng dự kiến từ đơn mua hàng đang mở |
| **Menu gọn** | Gom tiêu chuẩn kiểm tra · ẩn tình hình bàn giao · 1 lối giá thành/kho thành phẩm · nhóm mua nguyên phụ liệu |

### 5.4 Còn lại / thấp

| Hạng mục | Ghi chú | Ưu tiên |
|----------|---------|---------|
| **Nhiều nhà máy / kéo kanban / trả hàng khách → tái sản xuất** | Chỉ khi scale | Thấp |
| **Sinh lệnh hàng loạt từ kế hoạch** | Đã có sinh lệnh từ kế hoạch chi tiết | Đã có |
| **Làm dày quy trình / giá thành thực / xưởng** | MVP đã có; sâu theo pilot thực tế | Theo nhu cầu |

*Sidebar: URL cũ vẫn chạy; chỉ đổi nhãn tiếng Việt đầy đủ (giữ BOM).*

---

## 6. Điểm Portal đã hơn / khác AMIS (giữ nguyên)

1. **Hồ sơ SX / BOM / Costing** — lõi kỹ thuật
2. **Kho NPL SoT Portal** + bridge Odoo
3. **Đơn & TP qua KiotViet**
4. **Module Báo cáo NV** (hiệu suất ca/ngày) — không có tương đương trực tiếp trên AMIS demo

---

## 7. Lộ trình — trạng thái

```text
Giai đoạn 1 — “Chạy được một vòng SX”     ✅ xong
  D0→D3, P0→P3, C0→C1 (+ P4/P5, C2–C4)

Giai đoạn 2 — “Giống AMIS hơn ở vận hành” ✅ xong
  Q0→Q5, Dashboard tổng quan, sidebar QC

Giai đoạn 3 — “Bổ sung vận hành”          ✅ MVP + làm dày
  Giao việc, truy xuất, năng lực, BC vận hành, đóng gói, thuê GC
```

**Pilot đã chạy (2026-07-17) — `SP008073`:**

`KHTT → KHNVL → KHCT → LSX → YCX/PX posted → TKSX → QC → YCNTP ← KV PN002960 → Đóng gói → Truy xuất` — **pass**.  
UI Playwright: **15/15** màn.  
Script: `san_xuat/scripts/pilot_e2e_run.py`, `san_xuat/scripts/pilot_ui_pw_only.py`.

**Hướng làm tiếp đề xuất:** backlog §5 theo độ đau pilot thực tế (trả BTP / BOM tháo / dashboard extras) — không mở feature AMIS mới nếu chưa có nhu cầu.

---

## 8. Chi tiết hóa theo Garment ERP Spec (tham chiếu)

Nguồn: `C:\Users\Vuong-IT\Downloads\Garment_ERP_Vibe_Coding_Spec.md`.

### 8.1 Workflow chuẩn

```text
Đơn hàng (KV/CRM)
  -> Hồ sơ SX + BOM + Routing
  -> Kế hoạch SX (cân đối tồn + năng lực)
  -> Lệnh SX (MO/LSX)
  -> Giao việc theo công đoạn
  -> Ghi nhận sản lượng (đạt/lỗi)
  -> QC + cảnh báo vượt ngưỡng lỗi
  -> Nhập kho thành phẩm (tham chiếu KV)
```

Portal **đã cover** chuỗi chính; còn mỏng: routing đa CĐ (trả BTP), lương sản phẩm từ WorkLog, inbound dự kiến trong shortfall.

### 8.2–8.4 Acceptance D/Q/P

Giữ ý nghĩa acceptance gốc; **D0–D3, Q0–Q4, P0–P3 đã đạt** trên code + pilot. Chi tiết bug đã sửa khi pilot: `approve_material_issue` (có đính kèm) phải persist FK `stock_issue` và refresh status sau `post_stock_issue`.

### 8.5 Truy xuất nguồn gốc

Chuỗi tối thiểu đã có:

`lô ĐG / KV / YCNTP → LSX → YCX → StockIssueLine(batch) → lô NPL`  
(+ timeline TKSX, QC, GV, GC; tra ngược theo mã lô NPL).

### 8.6 Entity ổn định

| Spec | Portal |
|------|--------|
| ManufacturingOrder | `SxProductionOrder` |
| MaterialIssueRequest + StockIssue | `SxMaterialIssueRequest` → `kho_npl.StockIssue` |
| WorkLog / ProductionStat | `SxProductionStat` |
| QCInspection | `SxQcInspection` (+ criteria/defect lines) |
| FgReceiptRequest | `SxFgReceiptRequest` (+ `kv_purchase_*`) |

---

## 9. Checklist tiến độ

### Giai đoạn 1

- [x] D0 — LSX CRUD + release + BOM
- [x] D1 — YCX → phiếu xuất `kho_npl`
- [x] D2 — TKSX cập nhật LSX
- [x] D3 — YCNTP + link KV
- [x] P0 — KHTT CRUD + dòng SP
- [x] P1 — Lấy dòng từ đơn KV
- [x] P2 — KH NVL + shortfall
- [x] P3 — YCM + duyệt
- [x] C0 — List GT live từ BOM
- [x] C1 — Bảng GT định mức chốt kỳ

### Giai đoạn 2

- [x] Q0 — Danh mục QC
- [x] Q1 — YCKT
- [x] Q2 — PKT + kết luận
- [x] Q4 — Nối TKSX/LSX
- [x] Dashboard tổng quan (KPI + chart)
- [x] Sidebar QC nested “Tiêu chuẩn”

### Giai đoạn 3

- [x] Giao việc gắn LSX *(+ WorkTask portal, tổ/chuyền, filter TT)*
- [x] Truy xuất nguồn gốc *(timeline + tra ngược lô NPL)*
- [x] Năng lực SX *(tải kỳ vs NL / tận dụng TKSX)*
- [x] Báo cáo vận hành SX *(lọc SP/CĐ, drill-down, CSV, chart)*
- [x] Đóng gói *(dòng size/SKU, gắn YCNTP, tự sinh lô)*
- [x] Thuê gia công *(xuất/nhận NVL-BTP, TT gửi→nhận→xong)*

**Pilot E2E + UI:** xem §7.

---

## 10. Tài liệu khảo sát AMIS (raw)

Thư mục workspace (ngoài / cạnh repo docs):

| Thư mục | Nội dung |
|---------|----------|
| `_amis_plan_survey/` | Menu + màn kế hoạch SX (`d:\Project\`) |
| `_amis_dispatch_survey/` | Điều phối & thực thi |
| `_amis_qc_survey/` | Kiểm tra chất lượng |
| `_amis_costing_survey/` | Giá thành kế hoạch |
| `PortalJustPlay/_amis_survey/` | Đơn đặt hàng (2026-08-07, tenant OMIGA) |

Doc tổng hợp ĐĐH: [`don-dat-hang.md`](./don-dat-hang.md).

---

*Cập nhật: 2026-07-17 — GĐ1–3 xong; §5 viết lại ưu tiên cao/trung bình (factory ops) bằng tiếng Việt đầy đủ; nhãn UI không viết tắt (giữ BOM).*
