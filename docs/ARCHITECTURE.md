# Kiến trúc Portal Just Play

Tài liệu tổng quan cho người mới tham gia: các module có gì, gắn với URL nào,
liên quan nhau ra sao, và quy ước code chung.

---

## 1. Tổng quan

Portal là một **Django project đơn khối (monolith)** gồm ~20 app nghiệp vụ chạy
chung một database PostgreSQL và một tiến trình Gunicorn. Không có microservice;
các module giao tiếp trực tiếp qua ORM và import Python.

```
Người dùng ──▶ nginx ──▶ Gunicorn (PortalJustPlay.wsgi)
                              │
                    ┌─────────┴─────────┐
                    │   ~20 Django app  │
                    └─────────┬─────────┘
                              │
                    PostgreSQL (1 DB dùng chung)
                              │
        Tích hợp ngoài: KiotViet · Odoo · Synology NAS · Gemini · RustDesk
```

- **Điểm vào cấu hình:** `PortalJustPlay/settings.py`
- **Bảng định tuyến gốc:** `PortalJustPlay/urls.py`
- **Xác thực:** dùng `django.contrib.auth`; đăng nhập qua `audit.views_login.PortalLoginView`
  (có khoá tài khoản/IP). Hồ sơ nhân viên mở rộng bằng `hrm.Profile`.
- **Phân quyền:** theo phòng ban/chức danh — `hrm.RoleModulePermission`,
  `DepartmentMenuPermission`, `PermissionGroup`.
- **PWA:** service worker + manifest (`PortalJustPlay/pwa.py`), có Web Push.

---

## 2. Danh sách module

Mỗi app là một Django app chuẩn (`models.py`, `views.py`, `urls.py`, `templates/`,
`tests.py`). Cột **URL gốc** khớp với `PortalJustPlay/urls.py`.

### Nhân sự & tổ chức

| App            | URL gốc         | Vai trò | Model chính |
|----------------|-----------------|---------|-------------|
| `hrm`          | (nhiều nơi)     | Lõi tổ chức: phòng ban, chức danh, hồ sơ nhân viên, phân quyền module, sổ tay hướng dẫn | `Department`, `Division`, `Profile`, `RoleModulePermission`, `UserGuide` |
| `recruitment`  | `/hr/`          | Tuyển dụng | `JobPosting`, `Candidate`, `Interview` |
| `training`     | `/training/`    | Đào tạo nội bộ: khoá học, chương, bài, tiến độ | `Course`, `Chapter`, `Lesson`, `Enrollment`, `LessonProgress` |
| `assessment`   | `/` (trang chủ) | Đánh giá năng lực, ngân hàng câu hỏi, bài thi | `Competency`, `Exam`, `ExamSubmission`, `UserAnswer` |
| `kpi`          | `/kpi/`         | KPI theo kỳ/năm | `KpiPeriod`, `YearlyKpi`, `YearlyKpiItem` |

### Vận hành & công việc

| App               | URL gốc        | Vai trò | Model chính |
|-------------------|----------------|---------|-------------|
| `tasks`           | `/cong-viec/`  | Quản lý công việc, dự án nội bộ, việc lặp lại, bàn giao | `WorkTask`, `WorkTaskRecurrence`, `InternalProject`, `WorkTaskHandoff` |
| `service_requests`| `/yeu-cau/`    | Yêu cầu nội bộ nhiều bước (mua sắm, báo giá NCC…) | `ServiceRequest`, `RequestType`, `ProcurementLineItem`, `ServiceRequestStep` |
| `reports`         | `/reports/`    | Báo cáo công việc ngày/tuần, sản lượng ca sản xuất | `DailyWorkReport`, `WeeklyWorkReport`, `ProductionShiftProduct` |
| `feedback`        | `/gop-y/`      | Góp ý | `Feedback` |
| `surveys`         | `/khao-sat/`   | Khảo sát nội bộ | `Survey`, `SurveyResponse` |

### Kho & thiết bị

| App           | URL gốc        | Vai trò | Model chính |
|---------------|----------------|---------|-------------|
| `kho_npl`     | `/kho-npl/`    | Kho Nguyên Phụ Liệu: nhập/xuất/chuyển/kiểm kê/điều chỉnh, sổ cái tồn kho | `Material`, `StockBalance`, `StockReceipt`, `StockIssue`, `StockLedger`, `Stocktake` |
| `equipment`   | `/thiet-bi/`   | Quản lý thiết bị + tem QR, lịch bảo trì | `Device`, `DeviceCategory`, `MaintenanceLog` |

### Tài liệu, truyền thông & lưu trữ

| App            | URL gốc          | Vai trò | Model chính |
|----------------|------------------|---------|-------------|
| `documents`    | `/tai-lieu/`     | Thư viện tài liệu nội bộ + hỏi đáp AI (Gemini) | `Document`, `DocumentCategory`, `LibraryQAChatMessage` |
| `announcements`| `/announcements/`| Thông báo + theo dõi đã đọc | `Announcement`, `AnnouncementRead` |
| `nas_storage`  | `/thu-muc-nas/`  | Duyệt & phân quyền thư mục Synology NAS, chia sẻ link | `NasShareFolder`, `NasFolderPermission`, `NasUserFolderAcl` |

### Tích hợp bên ngoài

| App        | URL gốc       | Vai trò | Model chính |
|------------|---------------|---------|-------------|
| `kiotviet` | `/kiotviet/`  | Đồng bộ dữ liệu KiotViet (sản phẩm, tồn, đơn, hoá đơn…) + đẩy sang Odoo | `KvSyncState`, `KvProductInventory`, `KvSyncJob` |
| `odoo`     | `/odoo/`      | SSO Portal → Odoo, đồng bộ tài khoản (không có models riêng — service/scripts) | — |

### Hệ thống & tiện ích

| App         | URL gốc        | Vai trò | Model chính |
|-------------|----------------|---------|-------------|
| `audit`     | `/nhat-ky/`    | Nhật ký thao tác, bảo mật đăng nhập (khoá TK/IP), backup, RustDesk host | `UserActivityLog`, `UserLoginLock`, `PortalBackupJob`, `RustDeskHost` |
| `utilities` | `/tien-ich/`   | Đặt cơm, ứng lương, nhắc lịch, đăng ký Web Push | `MealOrder`, `SalaryAdvanceRequest`, `ScheduleReminder`, `MealPushSubscription` |
| `tools`     | `/cong-cu/`    | Công cụ lặt vặt (ghi chú cá nhân…) | `UserNote` |

---

## 3. Sơ đồ phụ thuộc giữa các app

`hrm` là trung tâm — hầu hết app tham chiếu `User`/`hrm.Profile`/`Department` để
phân quyền và gắn "người phụ trách". `audit` được nhiều app gọi để ghi nhật ký.

```
                     ┌──────────────┐
      ghi log ──────▶│    audit     │◀────── đăng nhập / bảo mật
                     └──────────────┘
                            ▲
   phân quyền, phòng ban,   │
   người phụ trách          │
   ┌────────────────────────┴────────────────────────┐
   │                     hrm (lõi)                    │
   └────────────────────────┬────────────────────────┘
        ▲        ▲          │          ▲        ▲
        │        │          │          │        │
     tasks   reports   service_req.  kho_npl  equipment  … (mọi app nghiệp vụ)

   nas_storage ──▶ reports/announcements (lưu file báo cáo lên NAS)
   kiotviet    ──▶ odoo (đẩy sản phẩm/tồn sang ERP)
   utilities   ──▶ Web Push (nhắc đặt cơm, nhắc lịch)
   documents   ──▶ Gemini (hỏi đáp thư viện)
```

Nguyên tắc: **không import ngược vào `hrm`**; các app dùng khoá ngoại tới
`hrm`/`auth.User` chứ `hrm` không phụ thuộc app nghiệp vụ.

---

## 4. Trạng thái kiểm thử

| Có test tương đối đầy đủ | Có test cơ bản | Cần bổ sung test |
|--------------------------|----------------|-------------------|
| `hrm`, `audit`, `tasks`, `service_requests`, `nas_storage`, `equipment`, `kiotviet` | `documents`, `reports`, `tools`, `assessment`, `feedback`, `utilities`, `kpi` | `announcements`, `recruitment`, `surveys`, `training`, `kho_npl` |

Chạy: `python manage.py test <app>`

---

## 5. Quy ước code

- **Ngôn ngữ:** giao diện & verbose_name bằng tiếng Việt; định danh code
  (biến/hàm/class) bằng tiếng Anh. URL slug tiếng Việt không dấu (`/cong-viec/`,
  `/yeu-cau/`).
- **App layout:** tách logic nặng ra `services/` (xem `audit/services`,
  `equipment/services`, `kho_npl`); view giữ mỏng.
- **Lệnh quản trị:** mọi tác vụ seed/đồng bộ/cron đặt trong
  `<app>/management/commands/` — không viết script rời rạc.
- **Cấu hình:** đọc qua biến môi trường (`os.getenv`) trong `settings.py`; giá trị
  mặc định an toàn cho local. Không hardcode secret — dùng `.env`.
- **Migrations:** commit kèm thay đổi model; không sửa migration đã merge.
- **Media/tài liệu:** file lưu qua `MEDIA_ROOT` hoặc NAS; `django-cleanup` tự dọn
  file mồ côi (bật bằng `CLEANUP_ORPHAN_MEDIA`).
- **Ghi nhật ký nghiệp vụ:** dùng `audit` cho hành động nhạy cảm thay vì log tự do.

---

## 6. Môi trường & triển khai

- **local vs production:** quyết định bởi `DJANGO_ENV`/`IS_PRODUCTION` trong
  `settings.py` → chọn `DB_DEFAULTS` và cờ bảo mật cookie/HTTPS.
- **Docker:** `docker-compose.yml` (db + web). Bản SSL: `docker-compose.ssl.yml`.
- **CI:** `.github/workflows/deploy.yml` (hiện chỉ deploy — nên bổ sung bước
  chạy test/lint trước khi deploy).
- **Tài liệu liên quan:** `docs/HUONG_DAN_AUTO_DEPLOY.md`,
  `docs/RUSTDESK_SELF_HOST.md`, `docs/ODOO_PHASE0.md`, `docs/integrations/`.
