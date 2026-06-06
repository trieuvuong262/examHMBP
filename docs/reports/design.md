# Thiết kế module Báo cáo — Sản xuất & Văn phòng (Ngày + Tuần)

> Phiên bản: **1.1** · PortalJustPlay · Just Play  
> Căn cứ: mẫu Excel **«TÍNH NĂNG SUẤT THEO NGÀY»** (phòng SX) + nhu cầu tách VP/SX

---

## 0. Quyết định đã chốt (28/05/2026)

| # | Câu hỏi | Quyết định |
|---|---------|------------|
| 1 | Công thức tổng HS% | **100% theo file Excel gốc** — port đúng công thức cell (dòng + TỔNG); unit test khớp mẫu 68,38% / 37,22% / 58,54% |
| 2 | BC tuần SX | **NV bắt buộc nộp** (không chỉ HOD xem tổng hợp) |
| 3 | Phòng lai (vừa xưởng vừa VP) | Profile **`HYBRID`** — **cùng lưới ô như Excel**, cột free text; ĐM/giờ/HS% tính khi đủ số |
| 4 | Một NV / ngày / ca | **Tách theo ca** — mỗi ca một báo cáo: `unique (employee, report_date, shift)` |

---

## 1. Mục tiêu

| # | Mục tiêu |
|---|----------|
| 1 | **Báo cáo ngày SX** khớp mẫu Excel: mã hàng, công đoạn, SL, định mức/h, giờ, **hiệu suất %** |
| 2 | **Báo cáo ngày VP** — form riêng (phòng VP thuần); **phòng lai** dùng lưới Excel free text |
| 3 | **Báo cáo tuần SX** — tổng hợp từ báo cáo ngày + ghi chú tuần |
| 4 | **Báo cáo tuần VP** — tự nhập: thành tựu, kế hoạch, vướng mắc |
| 5 | Giữ quy trình hiện tại: **Nháp → Nộp → HOD xem / phản hồi** |
| 6 | Tự chọn form theo **phòng ban** (cấu hình HR), không bắt NV chọn |

---

## 2. Ma trận loại báo cáo

|  | **Ngày** | **Tuần** |
|--|----------|----------|
| **Sản xuất** | Năng suất **theo ca** (Excel) | NV **nộp** BC tuần + tổng hợp từ BC ngày/ca |
| **Văn phòng** | Danh sách công việc trong ngày | NV nộp — tổng kết tuần |
| **Lai (HYBRID)** | Lưới ô như Excel, **free text** | Giống SX tuần — NV nộp |

**Khác module Công việc (`tasks`):**

- **Báo cáo** = nhật ký định kỳ (ngày/tuần), không có luồng giao–nhận–duyệt từng task.
- **Công việc** = nhiệm vụ cụ thể có người giao, hạn, duyệt hoàn thành.

---

## 3. Báo cáo ngày — Sản xuất (khớp Excel)

### 3.1. Màn hình «Báo cáo hôm nay» (SX)

**Header (read-only + chọn ca):**

| Trường | Nguồn |
|--------|--------|
| Tên nhân viên | `Profile.full_name` |
| Bộ phận | `Department.name` (+ `Division.name` nếu có) |
| Ngày | Chọn / mặc định hôm nay |
| Ca làm | Sáng / Chiều / Đêm — **mỗi ca = 1 báo cáo riêng** |

**Chọn ca:** URL `?date=…&shift=MORNING` — nộp xong ca Sáng vẫn có thể mở ca Chiều cùng ngày.

**Bảng dòng (giống Excel):**

| STT | Cột UI | Field DB | Bắt buộc | Ghi chú |
|-----|--------|----------|----------|---------|
| 1 | Mã hàng | `product_code` | Không* | Gợi ý từ KiotViet (phase 2) |
| 2 | Công đoạn | `process_name` | **Có** | Text tự do: *kansai lai áo*, *VS lai tay* |
| 3 | Số lượng | `quantity` | **Có** | Số nguyên ≥ 0 |
| 4 | Định mức/h | `norm_per_hour` | **Có** | Số thập phân > 0; gợi ý từ danh mục |
| 5 | Thời gian (h) | `hours_spent` | **Có** | Số thập phân > 0, bước 0,5 |
| 6 | Hiệu suất | *(tính)* | — | Chỉ hiển thị, không nhập |
| 7 | Ghi chú | `note` | Không | Tuỳ chọn |

\* Ít nhất một trong `product_code` hoặc mô tả công đoạn đủ rõ.

**Dòng TỔNG (footer, read-only):**

| Chỉ tiêu | Công thức |
|----------|-----------|
| Tổng số lượng | `Σ quantity` |
| Tổng thời gian | `Σ hours_spent` (hiển thị `9,5h`) |
| Hiệu suất chung | **Công thức cell TỔNG trong file Excel gốc** |

**Công thức — bắt buộc khớp Excel 100%:**

- Code trong `reports/services/efficiency.py`; **unit test regression** từ mẫu bên dưới.
- Khi có file `.xlsx` gốc: đọc formula từng dòng HS% và ô TỔNG → port sang Python (`Decimal`).
- Làm tròn hiển thị **2 chữ số thập phân** như Excel.

**Bộ test chuẩn:**

| Công đoạn | SL | ĐM/h | Giờ | HS% (mong đợi) |
|-----------|-----|------|-----|----------------|
| kansai lai áo | 400 | 90 | 6,5 | **68,38%** |
| VS lai tay | 115 | 103 | 3 | **37,22%** |
| **TỔNG** | **515** | — | **9,5h** | **58,54%** |

Kết quả code khác mẫu → sửa code, không đổi kỳ vọng test.

**Validation:**

- Tối thiểu **1 dòng** hợp lệ khi nộp.
- `norm_per_hour > 0`, `hours_spent > 0`, `quantity ≥ 0`.
- Cảnh báo (không chặn): HS% < 50% → badge vàng trên dòng.

**Tiện ích giữ từ hiện tại:**

- Lưu nháp / Nộp cho cấp trên
- Sao chép hôm qua (copy toàn bộ dòng, reset ngày)
- Lịch sử cá nhân
- Sửa sau khi đã nộp

**Bỏ / thay thế so với code cũ:**

- Bỏ dropdown `area` cố định (Cắt/May/QC…) → thay bằng `process_name` text.
- Bỏ `product_name`, `unit` trên dòng SX (hoặc giữ `product_name` optional phía sau phase 2).
- `order_code` đổi tên thành `product_code` (mã hàng).

---

## 4. Báo cáo ngày — Văn phòng & phòng lai

### 4.0. Phòng lai (`HYBRID`)

- **Cùng UI bảng** như SX (Mã hàng · Công đoạn · SL · ĐM/h · Giờ · HS% · Ghi chú).
- Cột **free text** — không bắt buộc đủ bộ SX; NV điền theo việc thực tế (VP + xưởng).
- HS% chỉ tính khi dòng có đủ `quantity`, `norm_per_hour`, `hours_spent` > 0.
- Dòng thiếu số → bỏ qua trong TỔNG HS% (giống Excel bỏ ô trống).
- **Vẫn tách theo ca** như SX.

### 4.1. Màn hình «Báo cáo hôm nay» (VP thuần)

**Header:** Tên NV, Phòng ban, Ngày (không có Ca).

**Bảng dòng:**

| Cột | Field | Bắt buộc |
|-----|-------|----------|
| Nội dung công việc | `task_title` | Có |
| Mô tả / kết quả | `result_note` | Không |
| Thời gian (h) | `hours_spent` | Có |
| Trạng thái | `status` | Có — `DONE` / `IN_PROGRESS` / `BLOCKED` |
| Ghi chú | `note` | Không |

**Footer:**

| Chỉ tiêu | Công thức |
|----------|-----------|
| Tổng giờ | `Σ hours_spent` |
| Số việc hoàn thành | Đếm `status = DONE` |

Không có hiệu suất %.

---

## 5. Báo cáo tuần — Sản xuất

### 5.1. Hai phần: Tổng hợp tự động + Nhận xét tay

**Tuần:** ISO (Thứ 2 → Chủ nhật), chọn bằng `week_start` (date thứ 2).

**Phần A — Bảng tổng hợp (read-only, từ BC ngày):**

Gộp tất cả `ProductionReportLine` trong tuần của NV:

| Nhóm | Cột |
|------|-----|
| Theo **công đoạn** | process_name, tổng SL, tổng giờ, HS% |
| Theo **mã hàng** | product_code, tổng SL, tổng giờ, HS% |
| **Tổng tuần** | SL, giờ, HS% (cùng công thức tổng như ngày) |

Biểu đồ tuỳ chọn (phase 2): HS% theo ngày trong tuần.

**Phần B — Form tuần (nhập / nộp):**

| Field | Mô tả |
|-------|--------|
| `summary_note` | Tóm tắt tuần (NV) |
| `issues_note` | Sự cố / vướng mắc |
| `plan_next_week` | Kế hoạch tuần sau |
| `hod_reviewed`, `hod_note` | Giống BC ngày |

**Trạng thái:** Nháp / Đã nộp — **NV bắt buộc nộp** trước deadline (mặc định 12:00 thứ 2 tuần sau, cấu hình được).

**Phần tổng hợp:** read-only từ tất cả BC ngày/ca trong tuần.

**Khi nộp:** bắt buộc điền ít nhất `summary_note` hoặc xác nhận «đã xem bảng tổng hợp».

**Cảnh báo HOD:** thiếu ca/ngày trong tuần → hiển thị đỏ trên team tuần.

---

## 6. Báo cáo tuần — Văn phòng

**Form tuần thuần nhập:**

| Field | Mô tả |
|-------|--------|
| `achievements` | Việc đã hoàn thành trong tuần (richtext hoặc nhiều dòng) |
| `in_progress` | Việc đang làm dở |
| `plan_next_week` | Kế hoạch tuần tới |
| `blockers` | Vướng mắc cần hỗ trợ |
| `total_hours` | Tổng giờ (tự tính từ BC ngày VP nếu có, cho phép sửa) |

Có thể **gợi ý** từ tổng BC ngày VP trong tuần (danh sách việc DONE).

---

## 7. Mô hình dữ liệu

### 7.1. Cấu hình phòng ban

```python
class DepartmentReportConfig(models.Model):
    PROFILE_PRODUCTION = 'PRODUCTION'   # Excel strict
    PROFILE_OFFICE = 'OFFICE'           # Form VP (mục 4.1)
    PROFILE_HYBRID = 'HYBRID'           # Lưới Excel free text

    department = OneToOneField(Department)
    report_profile = CharField(choices=...)  # PRODUCTION | OFFICE | HYBRID
    require_daily = BooleanField(default=True)
    require_weekly = BooleanField(default=True)
    weekly_submit_deadline_weekday = SmallIntegerField(default=0)   # 0=Mon
    weekly_submit_deadline_hour = SmallIntegerField(default=12)
```

HR cấu hình tại **Nhân sự → Phòng ban**: «Mẫu báo cáo: Sản xuất / Văn phòng / Lai (Excel)».

### 7.2. Header thống nhất (thay `DailyWorkReport`)

```python
class WorkReport(models.Model):
    KIND_PROD_DAILY = 'PROD_DAILY'
    KIND_OFFICE_DAILY = 'OFFICE_DAILY'
    KIND_PROD_WEEKLY = 'PROD_WEEKLY'
    KIND_OFFICE_WEEKLY = 'OFFICE_WEEKLY'

    employee = FK(User)
    report_kind = CharField(choices=...)
    report_date = DateField(null=True)      # daily
    week_start = DateField(null=True)       # weekly (Monday)
    shift = CharField(null=True)            # PROD_DAILY / HYBRID daily — bắt buộc
    status = DRAFT | SUBMITTED
    submitted_at = DateTimeField(null=True)
    hod_reviewed = BooleanField
    hod_note = CharField(500)

    # Weekly text fields (nullable by kind)
    summary_note = TextField(blank=True)
    issues_note = TextField(blank=True)
    plan_next_week = TextField(blank=True)
    achievements = TextField(blank=True)   # OFFICE_WEEKLY
    in_progress = TextField(blank=True)
    blockers = TextField(blank=True)

    class Meta:
        constraints = [
            # Mỗi NV / ngày / ca / loại ngày — tách ca
            UniqueConstraint(
                fields=['employee', 'report_date', 'shift', 'report_kind'],
                condition=Q(report_date__isnull=False, shift__isnull=False),
                name='uniq_daily_per_shift',
            ),
            UniqueConstraint(
                fields=['employee', 'report_date', 'report_kind'],
                condition=Q(report_date__isnull=False, shift__isnull=True),
                name='uniq_daily_no_shift',
            ),
            UniqueConstraint(
                fields=['employee', 'week_start', 'report_kind'],
                condition=Q(week_start__isnull=False),
                name='uniq_weekly',
            ),
        ]
```

### 7.3. Dòng báo cáo ngày SX

```python
class ProductionDailyLine(models.Model):
    report = FK(WorkReport, related_name='production_lines')
    product_code = CharField(80, blank=True)
    process_name = CharField(120)
    quantity = PositiveIntegerField
    norm_per_hour = DecimalField(max_digits=8, decimal_places=2)
    hours_spent = DecimalField(max_digits=5, decimal_places=2)
    note = CharField(255, blank=True)
    sort_order = PositiveSmallIntegerField

    @property
    def efficiency_pct(self):
        denom = self.norm_per_hour * self.hours_spent
        if not denom:
            return None
        return round(self.quantity / denom * 100, 2)
```

### 7.4. Dòng báo cáo ngày VP

```python
class OfficeDailyLine(models.Model):
    report = FK(WorkReport, related_name='office_lines')
    task_title = CharField(200)
    result_note = TextField(blank=True)
    hours_spent = DecimalField(max_digits=5, decimal_places=2)
    status = CharField  # DONE | IN_PROGRESS | BLOCKED
    note = CharField(255, blank=True)
    sort_order = PositiveSmallIntegerField
```

### 7.5. Danh mục định mức (phase 2, tuỳ chọn)

```python
class ProcessNorm(models.Model):
    """HR/KHSX maintain — gợi ý định mức khi NV gõ công đoạn."""
    product_code = CharField(80, blank=True)
    process_name = CharField(120)
    norm_per_hour = DecimalField(...)
    department = FK(Department, null=True)
    is_active = BooleanField(default=True)
```

Autocomplete: gõ `process_name` → điền `norm_per_hour` + gợi ý `product_code`.

### 7.6. Migration từ `DailyWorkReport`

| Cũ | Mới |
|----|-----|
| `DailyWorkReport` | `WorkReport` `PROD_DAILY` |
| `DailyWorkReportLine.area` | `process_name` = `get_area_display()` hoặc map |
| `order_code` | `product_code` |
| `quantity`, `note` | giữ |
| `product_name`, `unit` | bỏ hoặc gộp vào `note` khi migrate |

Script `migrate_daily_reports_to_v2` chạy một lần sau deploy.

---

## 8. Phân quyền & luồng (giữ nguyên tinh thần hiện tại)

| Vai trò | BC ngày (nộp) | BC tuần (nộp) | Xem team | Phản hồi HOD |
|---------|---------------|---------------|----------|--------------|
| Nhân viên | Có (theo profile phòng) | Có | Không | Không |
| Tổ trưởng / TBP | Có | Có | Có (subordinates) | Có |
| Giám đốc | Không | Không | Có | Có |

- Vẫn dùng `Profile.subordinates` (cấu hình Nhân sự).
- Module `reports` bật theo `DepartmentMenuPermission`.
- `can_submit_daily_report` → đổi tên `can_submit_work_report` (áp dụng cả tuần).

**Hub điều hướng (`/reports/`):**

```
NV SX      → /reports/today/?shift=MORNING   (Excel strict)
NV HYBRID  → /reports/today/?shift=…         (Excel free text)
NV VP      → /reports/today/                 (form VP, không shift*)
HOD        → /reports/team/                  (tab Ngày+ca | Tuần)
```
\* VP thuần: một BC/ngày, `shift` null.

---

## 9. Menu & URL

```
/reports/                          hub
/reports/today/                    BC ngày (auto form theo phòng)
/reports/today/?date=2026-05-28
/reports/week/                     BC tuần hiện tại
/reports/week/?week=2026-05-26     (week_start)
/reports/copy-yesterday/           SX + VP daily
/reports/my/                       Lịch sử (lọc: Ngày/Tuần)
/reports/team/                     HOD — tab Ngày | Tuần
/reports/<pk>/                     Chi tiết
/reports/export/daily.xlsx         Phase 2 — xuất giống Excel
/reports/admin/norms/              Phase 2 — danh mục định mức
```

**Sidebar «Báo cáo»** — submenu (mobile: accordion):

- Hôm nay
- Tuần này
- Lịch sử
- Cấp dưới *(nếu HOD)*

---

## 10. UI — Báo cáo ngày SX (wireframe)

```
┌─────────────────────────────────────────────────────────────┐
│ Báo cáo hôm nay — Năng suất                                 │
│ Nguyễn Văn A · Bộ phận May · [Ngày ▼] [Ca ▼]    [Lịch sử]  │
├─────────────────────────────────────────────────────────────┤
│ STT │ Mã hàng │ Công đoạn │ SL │ ĐM/h │ Giờ │ HS% │  ✕    │
│  1  │         │ kansai... │400 │  90  │ 6,5 │68,38│       │
│  2  │         │ VS lai... │115 │ 103  │  3  │37,22│       │
│ [+ Thêm dòng]                                               │
├─────────────────────────────────────────────────────────────┤
│ TỔNG │         │           │515 │      │ 9,5h│58,54│       │
├─────────────────────────────────────────────────────────────┤
│ [Lưu nháp]  [Nộp cho cấp trên]     [Sao chép hôm qua]      │
└─────────────────────────────────────────────────────────────┘
```

- HS% cập nhật **realtime** khi đổi SL / ĐM / Giờ (JS).
- Footer TỔNG sticky khi cuộn bảng dài.

---

## 11. UI — HOD xem team

**Tab «Theo ngày»** (giữ logic hiện tại + thêm cột HS% cho SX):

| NV | Trạng thái | Tổng SL | Tổng giờ | HS% | Chi tiết |
|----|------------|---------|----------|-----|----------|

**Tab «Theo tuần»:**

| NV | Đủ ngày? | Tổng SL tuần | HS% tuần | BC tuần | Chi tiết |
|----|----------|--------------|----------|---------|----------|

- «Đủ ngày?»: `số ngày đã nộp / số ngày làm việc kỳ vọng` (mặc định 6 ngày, cấu hình sau).

---

## 12. Widget trang chủ

| Đối tượng | Widget |
|-----------|--------|
| NV chưa nộp BC **ngày** | Đỏ — «Chưa nộp báo cáo hôm nay» |
| NV chưa nộp BC **tuần** (cuối tuần) | Vàng — «Chưa nộp báo cáo tuần» |
| HOD thiếu BC ngày team | Xanh — «N nhân viên chưa nộp hôm nay» |
| HOD thiếu BC tuần | «N nhân viên chưa nộp tuần» |

---

## 13. Tích hợp KiotViet (phase 2)

- Autocomplete **Mã hàng** từ `kv_product` (mirror).
- Không FK bắt buộc — vẫn cho nhập tay.
- Đối chiếu báo cáo SX vs tồn / đơn KV (báo cáo quản trị riêng).

---

## 14. Kế hoạch triển khai

| Phase | Phạm vi | Ước lượng |
|-------|---------|-----------|
| **P1** | Model `WorkReport` + `ProductionDailyLine`; form SX khớp Excel; migration; đổi UI `today.html` | 1 sprint |
| **P2** | `OfficeDailyLine` + `DepartmentReportConfig`; form VP | 0,5 sprint |
| **P3** | BC tuần SX (tổng hợp) + form nhận xét; tab team tuần | 1 sprint |
| **P4** | BC tuần VP; widget; submenu | 0,5 sprint |
| **P5** | `ProcessNorm` autocomplete; export Excel; biểu đồ | 1 sprint |

**P1 — checklist kỹ thuật:**

- [ ] Migration + data migrate `DailyWorkReport` → `WorkReport`
- [ ] `reports/forms.py` — `ProductionDailyLineFormSet` + tính HS%
- [ ] `reports/services/efficiency.py` — `line_efficiency`, `report_totals`
- [ ] Templates `today_production.html` (hoặc partial)
- [ ] Cập nhật `team.html`, `detail.html`, tests
- [ ] Cập nhật Hướng dẫn portal (mục 8)

---

## 15. Trạng thái spec

- **§0 Quyết định đã chốt** — đủ điều kiện triển khai **P1**.
- Cần file **Excel gốc** (`.xlsx`) khi code để copy chính xác công thức ô TỔNG.

**Bước tiếp theo:** triển khai P1 (BC ngày SX + HYBRID, tách ca, công thức Excel).

---

*Cập nhật: 28/05/2026 — v1.1*
