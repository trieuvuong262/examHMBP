# Thiết kế module Báo cáo — Sản xuất & Văn phòng (Ngày + Tuần)

> Phiên bản: **1.2** · PortalJustPlay · Just Play  
> Căn cứ: mẫu Excel **«TÍNH NĂNG SUẤT THEO NGÀY»** (phòng SX) + nhu cầu tách SX / phòng ban khác

---

## 0. Quyết định đã chốt (28/05/2026)

| # | Câu hỏi | Quyết định |
|---|---------|------------|
| 1 | Công thức tổng HS% | **100% theo file Excel gốc** — port đúng công thức cell (dòng + TỔNG); unit test khớp mẫu 68,38% / 37,22% / 58,54% |
| 2 | BC tuần SX | **NV bắt buộc nộp** (không chỉ HOD xem tổng hợp) |
| 3 | Phòng ban **không SX** (VP, KD, HCNS, IT, …) | **Chưa có mẫu cố định** → NV nhập **tự do kiểu Excel hoặc Word** (chọn tab trên cùng một màn) |
| 4 | Một NV / ngày / ca (chỉ SX) | **Tách theo ca** — mỗi ca một báo cáo: `unique (employee, report_date, shift)` |
| 5 | Phòng SX vs phòng khác | **Hai luồng UI hoàn toàn khác** — menu chung nhưng form tự chọn theo `report_profile` phòng ban |

---

## 1. Mục tiêu

| # | Mục tiêu |
|---|----------|
| 1 | **Báo cáo ngày SX** khớp mẫu Excel: mã hàng, công đoạn, SL, định mức/h, giờ, **hiệu suất %** |
| 2 | **Báo cáo ngày phòng khác** — nhập tự do **Bảng Excel** hoặc **Văn bản Word** (chưa ép mẫu cột) |
| 3 | **Báo cáo tuần SX** — tổng hợp từ báo cáo ngày/ca + ghi chú tuần |
| 4 | **Báo cáo tuần phòng khác** — cùng cơ chế Excel / Word tự do (không form cố định) |
| 5 | Giữ quy trình hiện tại: **Nháp → Nộp → HOD xem / phản hồi** |
| 6 | Tự chọn form theo **phòng ban** (cấu hình HR), không bắt NV chọn |

---

## 2. Ma trận loại báo cáo

|  | **Ngày** | **Tuần** |
|--|----------|----------|
| **Sản xuất (`PRODUCTION`)** | Bảng năng suất **theo ca**, khớp Excel SX (ĐM/h, HS%) | NV **nộp** + bảng tổng hợp tự động từ BC ngày/ca |
| **Phòng ban khác (`OFFICE`)** | Tab **Excel** (lưới ô tự do) hoặc tab **Word** (soạn thảo rich text) | Cùng hai tab — NV tự chọn kiểu nhập phù hợp tuần đó |

**Mặc định:** phòng ban chưa cấu hình → `OFFICE` (nhập tự do). Chỉ phòng SX được HR gán `PRODUCTION`.

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

## 4. Báo cáo ngày — Phòng ban khác (không SX)

> **Nguyên tắc:** HR chưa ban hành mẫu Excel/Word riêng cho từng phòng → portal **không ép cột cố định**. NV tự soạn như đang làm trên file Excel hoặc Word ngoài.

### 4.1. Màn hình «Báo cáo hôm nay» (OFFICE)

**Header (read-only):** Tên NV · Phòng ban · Ngày (chọn ngày). **Không có Ca** — một báo cáo / ngày / NV.

**Hai tab trên cùng một báo cáo** (lưu chung `WorkReport`, nội dung theo tab đang chọn):

| Tab | Kiểu nhập | Mô tả |
|-----|-----------|--------|
| **Bảng Excel** | Lưới ô tự do | Giống spreadsheet: thêm/xóa dòng, thêm/xóa cột, đổi tên cột, gõ text/số vào ô |
| **Văn bản Word** | Rich text (CKEditor) | Soạn thảo tự do: đoạn văn, danh sách, bảng nhúng, ảnh (upload CKEditor) |

**Tab Excel — hành vi:**

- Mặc định **3 cột trống** + **5 dòng** (NV tự đặt tên cột, ví dụ «Việc làm», «Kết quả», «Ghi chú»).
- Nút: `[+ Dòng]` `[+ Cột]` `[− Dòng]` `[− Cột]` — chỉ ảnh hưởng tab Excel.
- Ô: text tự do (không validate công thức, không HS%).
- Có thể **dán từ Excel** (paste nhiều ô — phase 2; P1: nhập tay).
- Lưu JSON: `{ "columns": ["...", ...], "rows": [["...", ...], ...] }`.

**Tab Word — hành vi:**

- Editor CKEditor (đã có trên portal — `documents`, `hrm`).
- Lưu HTML đã sanitize (`bleach` / `RichTextField`).
- NV có thể chỉ dùng Word, chỉ dùng Excel, hoặc điền cả hai tab trong cùng một báo cáo.

**Validation khi nộp:**

- Ít nhất **một tab** có nội dung: Excel có ≥ 1 ô không trống **hoặc** Word có ≥ 50 ký tự text.
- Không bắt buộc điền cả hai tab.

**Tiện ích (giống SX):** Lưu nháp · Nộp · Lịch sử · Sửa sau nộp · Sao chép hôm qua (copy cả JSON + HTML).

**Khác SX:**

| | SX (`PRODUCTION`) | Phòng khác (`OFFICE`) |
|--|-------------------|------------------------|
| Ca làm | Có (Sáng/Chiều/Đêm) | Không |
| Cột cố định | Mã hàng, Công đoạn, SL, ĐM/h, Giờ, HS% | Không — NV tự đặt |
| Hiệu suất % | Có, khớp Excel gốc | Không |

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

## 6. Báo cáo tuần — Phòng ban khác

**Cùng nguyên tắc ngày:** chưa có mẫu HR → **tab Excel + tab Word**, NV tự soạn.

**Header:** Tên NV · Phòng ban · Tuần (chọn `week_start` = thứ 2).

**Không** tách field cố định (`achievements`, `blockers`, …). Khi HR sau này ban hành mẫu Word/Excel cho phòng X, cấu hình `DepartmentReportConfig.template_file` (phase sau) — P1/P2 vẫn để trống.

**Validation khi nộp:** giống BC ngày OFFICE (ít nhất một tab có nội dung).

**Tuỳ chọn (phase 2):** nút «Gợi ý từ báo cáo ngày» — chèn tóm tắt các BC ngày trong tuần (preview, NV chỉnh sửa trước khi nộp).

---

## 7. Mô hình dữ liệu

### 7.1. Cấu hình phòng ban

```python
class DepartmentReportConfig(models.Model):
    PROFILE_PRODUCTION = 'PRODUCTION'   # Bảng năng suất SX — mục 3
    PROFILE_OFFICE = 'OFFICE'           # Excel / Word tự do — mục 4, 6

    department = OneToOneField(Department)
    report_profile = CharField(choices=...)  # PRODUCTION | OFFICE (mặc định OFFICE)
    require_daily = BooleanField(default=True)
    require_weekly = BooleanField(default=True)
    weekly_submit_deadline_weekday = SmallIntegerField(default=0)   # 0=Mon
    weekly_submit_deadline_hour = SmallIntegerField(default=12)
```

HR cấu hình tại **Nhân sự → Phòng ban**: «Mẫu báo cáo: **Sản xuất** (Excel năng suất) hoặc **Phòng ban khác** (Excel/Word tự do)». Chỉ gán **Sản xuất** cho các bộ phận May/Cắt/QC/…; còn lại để mặc định hoặc chọn **Phòng ban khác**.

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
    shift = CharField(null=True)            # PROD_DAILY only — bắt buộc khi SX
    status = DRAFT | SUBMITTED
    submitted_at = DateTimeField(null=True)
    hod_reviewed = BooleanField
    hod_note = CharField(500)

    # Weekly SX — nhận xét tay (nullable)
    summary_note = TextField(blank=True)
    issues_note = TextField(blank=True)
    plan_next_week = TextField(blank=True)

    # OFFICE daily/weekly — nội dung tự do (mục 4, 6)
    freeform_mode = CharField(blank=True)   # SPREADSHEET | DOCUMENT | BOTH (tab cuối lưu)
    spreadsheet_json = JSONField(null=True, blank=True)
    document_html = TextField(blank=True)   # CKEditor, sanitize khi lưu

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

### 7.4. ~~Dòng báo cáo ngày VP~~ → bỏ (v1.2)

Không dùng `OfficeDailyLine` / form cột cố định. Phòng khác lưu trực tiếp trên `WorkReport`: `spreadsheet_json` + `document_html` (mục 7.2).

### 7.5. Danh mục định mức (phase 2, tuỳ chọn — chỉ SX)

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
NV phòng SX        → /reports/today/?shift=MORNING     (bảng năng suất, mục 3)
NV phòng khác      → /reports/today/                   (tab Excel | Word, mục 4)
NV phòng khác tuần → /reports/week/                    (tab Excel | Word, mục 6)
HOD                → /reports/team/                    (tab Ngày | Tuần — cột khác theo profile NV)
```

`report_profile` lấy từ `DepartmentReportConfig` của phòng NV; không có cấu hình → `OFFICE`.

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

**Sidebar «Báo cáo»** — submenu giống nhau mọi phòng (mobile: accordion); **nội dung trang** phân nhánh theo profile:

| Mục menu | NV phòng SX | NV phòng khác |
|----------|-------------|---------------|
| **Hôm nay** | Form năng suất + chọn **Ca** | Tab **Excel** / **Word**, không Ca |
| **Tuần này** | Tổng hợp BC ngày + ghi chú | Tab **Excel** / **Word** |
| **Lịch sử** | Giống nhau | Giống nhau |
| **Cấp dưới** *(HOD)* | Cột HS%, ca, SL | Cột «Đã nộp», xem preview Excel/Word |

```
Báo cáo ▾
├── Hôm nay
├── Tuần này
├── Lịch sử
└── Cấp dưới   (chỉ HOD)
```

Tiêu đề trang đổi theo profile: *«Báo cáo hôm nay — Năng suất»* (SX) vs *«Báo cáo hôm nay»* (phòng khác).

---

## 10. UI — Báo cáo ngày phòng khác (wireframe)

```
┌─────────────────────────────────────────────────────────────┐
│ Báo cáo hôm nay                                             │
│ Trần Thị B · Phòng KD · [Ngày ▼]                 [Lịch sử]  │
├─────────────────────────────────────────────────────────────┤
│  [ Bảng Excel ]  [ Văn bản Word ]                           │
├─────────────────────────────────────────────────────────────┤
│  │ Cột 1 ▼ │ Cột 2 ▼ │ Cột 3 ▼ │  [+ Cột]                  │
│  │ việc A  │ xong    │         │                           │
│  │ việc B  │ 50%     │ chờ duyệt│                          │
│  │         │         │         │                           │
│  [+ Dòng]  [− Dòng]                                         │
├─────────────────────────────────────────────────────────────┤
│ [Lưu nháp]  [Nộp cho cấp trên]     [Sao chép hôm qua]      │
└─────────────────────────────────────────────────────────────┘

Tab Word: vùng CKEditor full-width (toolbar: đậm, list, bảng, ảnh).
```

---

## 11. UI — Báo cáo ngày SX (wireframe)

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

## 12. UI — HOD xem team

**Tab «Theo ngày»** — cột theo profile từng NV:

| Profile NV | Cột hiển thị |
|------------|--------------|
| `PRODUCTION` | NV · Ca · Trạng thái · Tổng SL · Tổng giờ · HS% · Chi tiết |
| `OFFICE` | NV · Trạng thái · Kiểu (Excel/Word/Both) · Chi tiết |

**Tab «Theo tuần»:**

| Profile NV | Cột hiển thị |
|------------|--------------|
| `PRODUCTION` | NV · Đủ ngày/ca? · Tổng SL tuần · HS% tuần · BC tuần · Chi tiết |
| `OFFICE` | NV · Đã nộp tuần? · Chi tiết (xem Excel/Word) |

- «Đủ ngày?» (SX): số ca/ngày đã nộp / kỳ vọng (mặc định 6 ngày × ca, cấu hình sau).
- Chi tiết OFFICE: render preview bảng Excel hoặc HTML Word (read-only khi HOD xem).

---

## 13. Widget trang chủ

| Đối tượng | Widget |
|-----------|--------|
| NV chưa nộp BC **ngày** | Đỏ — «Chưa nộp báo cáo hôm nay» |
| NV chưa nộp BC **tuần** (cuối tuần) | Vàng — «Chưa nộp báo cáo tuần» |
| HOD thiếu BC ngày team | Xanh — «N nhân viên chưa nộp hôm nay» |
| HOD thiếu BC tuần | «N nhân viên chưa nộp tuần» |

---

## 14. Tích hợp KiotViet (phase 2)

- Autocomplete **Mã hàng** từ `kv_product` (mirror).
- Không FK bắt buộc — vẫn cho nhập tay.
- Đối chiếu báo cáo SX vs tồn / đơn KV (báo cáo quản trị riêng).

---

## 15. Kế hoạch triển khai

| Phase | Phạm vi | Ước lượng |
|-------|---------|-----------|
| **P1** | `WorkReport` + `ProductionDailyLine`; form **SX** khớp Excel; `DepartmentReportConfig`; routing theo profile | 1 sprint |
| **P2** | Form **phòng khác**: tab Excel (JSON grid) + tab Word (CKEditor); BC ngày/tuần OFFICE | 1 sprint |
| **P3** | BC tuần SX (tổng hợp) + nhận xét; tab team tuần SX | 1 sprint |
| **P4** | Submenu sidebar; widget; HOD preview Excel/Word | 0,5 sprint |
| **P5** | `ProcessNorm` autocomplete; export Excel SX; paste từ Excel; mẫu HR theo phòng (tuỳ chọn) | 1 sprint |

**P1 — checklist (phòng SX):**

- [ ] Migration + data migrate `DailyWorkReport` → `WorkReport`
- [ ] `reports/forms.py` — `ProductionDailyLineFormSet` + tính HS%
- [ ] `reports/services/efficiency.py` — `line_efficiency`, `report_totals`
- [ ] `today_production.html` + chọn ca
- [ ] `get_report_profile(user)` → redirect OFFICE sang form tự do (stub P2)

**P2 — checklist (phòng khác):**

- [ ] `spreadsheet_json` + `document_html` trên `WorkReport`
- [ ] JS grid Excel (thêm dòng/cột, đổi header)
- [ ] CKEditor tab Word + sanitize
- [ ] `today_freeform.html`, `week_freeform.html`
- [ ] Validation «ít nhất một tab có nội dung»

---

## 16. Trạng thái spec

- **§0 Quyết định đã chốt** — đủ điều kiện triển khai **P1** (SX) + **P2** (phòng khác).
- Cần file **Excel gốc SX** (`.xlsx`) khi code P1 để copy chính xác công thức ô TỔNG.
- Phòng khác: **không cần mẫu** trước khi code P2 — NV nhập tự do Excel/Word.

**Bước tiếp theo:** P1 (BC ngày SX, tách ca, HS%) song song chuẩn bị P2 (grid + CKEditor).

---

*Cập nhật: 28/05/2026 — v1.2 — tách SX / phòng khác; bỏ form VP cố định & profile HYBRID*
