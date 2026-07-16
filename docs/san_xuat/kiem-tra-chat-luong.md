# Thiết kế: Kiểm tra chất lượng (Portal)

> Nguồn khảo sát: AMIS Sản xuất demo — tenant **Công ty Cổ phần may** (2026-07-16).  
> Base path: `/production/product-quality/*`.  
> Menu Portal scaffold: [`hub-portal.md`](./hub-portal.md) § Kiểm tra chất lượng.  
> Upstream thực thi: [`dieu-phoi.md`](./dieu-phoi.md) (LSX / TKSX).

> Ghi chú: yêu cầu ghi “SMIS” — khảo sát trên **AMIS** (cùng demo MISA đã dùng cho kế hoạch / điều phối).

## 1. IA AMIS (benchmark)

Menu cấp 1 chỉ **3 mục**; danh mục nằm dưới **Tiêu chuẩn**:

```text
Kiểm tra chất lượng
├── Yêu cầu kiểm tra     /quality-check-request     YCKT*   QualityCheckRequest
├── Phiếu kiểm tra       /inspection-voucher        PKT*    InspectionVoucher
└── Tiêu chuẩn
    ├── Tiêu chí CL              /criteria                 QualityCriteria
    ├── Nhóm tiêu chí            /criteria-group           QualityCriteriaGroup
    ├── Phương pháp chọn mẫu     /sampling-method          SamplingMethod
    ├── Bộ tiêu chuẩn CL         /quality-standard         QualityStandard
    ├── Lỗi KTCL                 /quality-error            QualityError
    └── Nhóm lỗi KTCL            /quality-error-group      QualityErrorGroup
```

Landing Portal (`hub_qc.html`) **đã mirror** cấu trúc Vận hành / Tiêu chuẩn — giữ nguyên. Sidebar nếu đang flat 8 mục: nên gói 6 danh mục vào nested **Tiêu chuẩn** (giống kế hoạch / điều phối).

---

## 2. Luồng nghiệp vụ

```text
LSX / TKSX (điều phối)  ──hoặc──  thủ công
        │
        ▼
┌─────────────────────┐
│ Yêu cầu kiểm tra    │  YCKT  SP, LSX, công đoạn?, hạn, ưu tiên
│ (object: TP / CĐ)   │
└──────────┬──────────┘
           │ sinh phiếu
           ▼
┌─────────────────────┐
│ Phiếu kiểm tra      │  PKT   bộ TC + PP mẫu → SL mẫu đạt/không đạt
│                     │        kết luận Đạt / Không đạt
└──────────┬──────────┘
           │
           ├─► cập nhật TKSX / LSX (qty_defect)   [phase nối điều phối]
           └─► (optional) chặn YCNTP nếu không đạt
```

Danh mục (Tiêu chuẩn) phải có trước khi lập phiếu có ý nghĩa.

---

## 3. Field AMIS → Portal

### 3.1 Yêu cầu kiểm tra (`QualityCheckRequest` / YCKT)

| AMIS | Portal |
|------|--------|
| `QualityCheckRequestCode` | `code` |
| `RequestDate`, `CheckDeadline` | `request_date`, `due_at` |
| `InspectionPurpose` | `purpose`: `after_production` \| `after_stage` \| `other` |
| `ObjectType` (TP / Công đoạn / …) | `object_type`: `finished` \| `stage` |
| `ProductionOrderID`, `OrderNumber` | FK `production_order` null (sau D0 điều phối); interim: `mo_code` text |
| `InventoryItemCode/Name`, `CheckQuantity` | `product_code`, `product_name`, `qty` |
| `StageName` | `stage_name` / FK `ProcessStep` null |
| `PriorityLevel` | `priority` 1–5 |
| `Status` | `draft` \| `open` \| `in_progress` \| `done` \| `cancelled` |
| Đơn thuê GC / nhà máy | **Bỏ MVP** |

### 3.2 Phiếu kiểm tra (`InspectionVoucher` / PKT)

| AMIS | Portal |
|------|--------|
| `InspectionNo`, `InspectionDate` | `code`, `inspected_at` |
| `QualityCheckRequestCode` | FK `qc_request` |
| `QualityStandard` + `SamplingMethod` | FK `standard_set`, `sampling_method` |
| `SampleQuantity` / `ActualSampleQuantity` | `qty_sample_required`, `qty_sample_actual` |
| `MaxErrorAllowed` | tính từ PP mẫu hoặc nhập |
| `PassCount` / fail (SL mẫu đạt / không đạt) | `qty_pass`, `qty_fail` |
| `InspectionResult` Đạt / Không đạt | `result`: `pass` \| `fail` \| `pending` |
| `InspectionStatus` | `draft` \| `in_progress` \| `done` \| `cancelled` |
| Chi tiết tiêu chí / lỗi | `QcInspectionCriteriaLine`, `QcInspectionDefectLine` |

### 3.3 Danh mục tiêu chuẩn

| Thực thể AMIS | Portal model | Ghi chú |
|---------------|--------------|---------|
| `QualityCriteriaGroup` | `QcCriteriaGroup` | mã, tên, active |
| `QualityCriteria` | `QcCriteria` | kiểu (định tính/định lượng), nhóm, phương pháp kiểm tra |
| `SamplingMethod` | `QcSamplingMethod` | cố định SL / tỷ lệ % / theo khoảng SX; max lỗi |
| `QualityStandard` | `QcStandardSet` | áp dụng `product_code` (hoặc mọi SP), hiệu lực; M2M tiêu chí + default sampling |
| `QualityErrorGroup` | `QcDefectGroup` | cây nhóm (parent optional) |
| `QualityError` | `QcDefect` | severity, repairable, optional gắn tiêu chí |

**MVP sampling:** hỗ trợ `fixed_qty` và `percent`; bảng khoảng sản lượng phase sau.

---

## 4. SoT & biên

| Dữ liệu | SoT | Ghi chú |
|---------|-----|---------|
| YCKT / PKT / danh mục QC | Portal `san_xuat` | Mới |
| LSX / TKSX | Portal điều phối | FK khi D0–D2 xong; trước đó dùng mã text |
| BOM công đoạn | `ProcessStep` | object_type=stage |
| TP / đơn | KiotViet | chỉ snapshot mã SP |
| Odoo / AMIS | Không sync QC | |

---

## 5. Model đề xuất

```text
# Danh mục
QcCriteriaGroup(code, name, is_active)
QcCriteria(code, name, group FK, criteria_type: qualitative|quantitative,
           test_method_label, notes, is_active)
QcSamplingMethod(code, name, method_kind: fixed_qty|percent,
                 sample_qty, sample_pct, max_defect_qty, max_defect_pct, notes)
QcDefectGroup(code, name, parent FK null, is_active)
QcDefect(code, name, group FK null, severity, is_repairable,
         criteria FK null, notes, is_active)
QcStandardSet(code, name, product_code blank=all, effective_date,
              sampling_method FK null, notes, is_active)
QcStandardCriteria(standard FK, criteria FK, sort_order, min_value, max_value)  # optional bounds

# Vận hành
QcRequest(code, request_date, due_at, purpose, object_type,
          production_order FK null, mo_code, product_code, product_name,
          qty, stage_name, priority, status, requested_by, notes)
QcInspection(code, inspected_at, request FK, standard_set FK, sampling_method FK,
             qty_sample_required, qty_sample_actual, qty_pass, qty_fail,
             max_defect_allowed, result, status, inspector FK, notes)
QcInspectionCriteriaLine(inspection FK, criteria FK, value_text, value_number,
                         is_pass, notes)
QcInspectionDefectLine(inspection FK, defect FK, qty, notes)
```

Prefix: `YCKT`, `PKT`, mã danh mục do user nhập (TC/NM/PP/BTC/Lỗi…).

---

## 6. UX Portal (thiết kế lại)

### 6.1 Giữ URL hiện có

| URL | Vai trò |
|-----|---------|
| `/chat-luong/` | Landing 2 khối (đã có) + KPI: YCKT mở, PKT chờ làm |
| `/chat-luong/yeu-cau/` | List/CRUD YCKT; nút **Từ LSX / Từ TKSX** |
| `/chat-luong/phieu/` | List/CRUD PKT; tạo từ YCKT; nhập mẫu + kết luận |
| `/chat-luong/tieu-chi/` … `/nhom-loi/` | CRUD danh mục |

### 6.2 Sidebar

Gói nested giống AMIS:

```text
Kiểm tra chất lượng
├── Yêu cầu kiểm tra
├── Phiếu kiểm tra
└── Tiêu chuẩn ▾
    ├── Tiêu chí / Nhóm tiêu chí
    ├── PP chọn mẫu
    ├── Bộ tiêu chuẩn
    └── Lỗi / Nhóm lỗi
```

Keys quyền giữ nguyên (`qc_request`, `qc_sheet`, `qc_criteria`, …).

### 6.3 Không làm MVP

- Thuê gia công / vendor QC  
- AQL đầy đủ / bảng khoảng sản lượng phức tạp  
- App mobile QC AMIS  
- Đồng bộ AMIS/Odoo  

---

## 7. Thứ tự implement

| Phase | Scope | Done khi |
|-------|--------|----------|
| **Q0** | 6 model danh mục + admin/list CRUD | Tạo bộ TC + PP mẫu + vài tiêu chí/lỗi pilot |
| **Q1** | `QcRequest` CRUD (+ gắn `product_code` tay) | YCKT draft→open |
| **Q2** | `QcInspection` từ YCKT; tính SL mẫu từ PP; kết luận | PKT pass/fail |
| **Q3** | Dòng tiêu chí / lỗi trên phiếu | Ghi chi tiết được |
| **Q4** | Nối `ProductionOrder` / `ProductionStat` | Sinh YCKT từ TKSX; fail → cộng `qty_defect` |
| **Q5** | Nested sidebar + KPI landing | IA khớp AMIS |

Có thể **Q0 song song** điều phối D0; **Q4** sau D2.

---

## 8. Service

```text
san_xuat/services/qc.py
  compute_sample_qty(method, production_qty) -> (required, max_defect)
  create_inspection_from_request(request_id, standard_id=None) -> QcInspection
  finalize_inspection(inspection_id) -> result pass/fail; update request status
  create_request_from_stat(stat_id) -> QcRequest   # phase Q4
```

---

## 9. Khác biệt có chủ đích so với AMIS

1. **IA gọn như AMIS** (3 nhóm) nhưng URL/permission Portal giữ 8 key đã seed.  
2. **Gắn điều phối Portal** (LSX/TKSX), không kho QC AMIS.  
3. **Sampling đơn giản** trước; không clone toàn bộ AQL.  
4. **Bộ TC theo `product_code`** (KV/hồ sơ), không bắt buộc quy trình AMIS phức tạp — optional `process_label`.  
5. Kết quả QC ảnh hưởng xuất/nhập TP chỉ qua flag trên LSX/YCNTP (phase Q4), không dual-write kho.

---

## 10. Tiêu chí xong (MVP = Q0–Q2)

- [ ] CRUD đủ danh mục; có ≥1 bộ tiêu chuẩn + PP mẫu.  
- [ ] Tạo YCKT theo mã SP.  
- [ ] Sinh PKT từ YCKT; nhập SL mẫu; kết luận Đạt/Không đạt.  
- [ ] Landing hiện số phiếu chờ / yêu cầu mở.  
- [ ] Sidebar (hoặc landing) phản ánh nhóm **Tiêu chuẩn**.
