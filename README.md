# Portal Just Play

Portal nội bộ của **Just Play** — hệ thống Django 5.2 gom nhiều nghiệp vụ vào một cổng duy nhất: nhân sự, đánh giá năng lực, đào tạo, báo cáo, kho nguyên phụ liệu, quản lý thiết bị, thư mục NAS, tích hợp KiotViet & Odoo…

> Xem chi tiết kiến trúc và danh sách đầy đủ các module ở [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Công nghệ chính

| Thành phần   | Giá trị                                              |
|--------------|-----------------------------------------------------|
| Framework    | Django 5.2 + Django REST Framework                  |
| Python       | 3.13                                                 |
| Database     | PostgreSQL (15 trên production/Docker)              |
| WSGI server  | Gunicorn (3 workers) sau nginx                       |
| Editor       | CKEditor 4 LTS                                       |
| Tích hợp     | KiotViet API, Odoo (XML-RPC + SSO), Google Gemini, Synology NAS (rclone/LDAP/DSM), RustDesk, Web Push |
| Triển khai   | Docker Compose (db + web) + nginx; CI qua GitHub Actions |

---

## Chạy trên máy local (không Docker)

Portal dùng PostgreSQL cho cả local và production (không phải SQLite).

### 1. Cài PostgreSQL và tạo database

Mặc định local dùng database tên **`hrms_db`** trên `127.0.0.1:5432`, user `postgres`
(xem `DB_DEFAULTS` trong `PortalJustPlay/settings.py`).

```sql
CREATE DATABASE hrms_db;
```

### 2. Cài package

```powershell
pip install -r requirements.txt
```

### 3. Cấu hình `.env`

Sao chép `.env.example` → `.env` rồi chỉnh cho môi trường local. Tối thiểu cần:

```dotenv
DJANGO_ENV=local
DEBUG=True
SECRET_KEY=dev-secret-key-doi-thanh-gia-tri-rieng
DB_NAME=hrms_db
DB_USER=postgres
DB_PASSWORD=<mật khẩu postgres của bạn>
DB_HOST=127.0.0.1
DB_PORT=5432
```

> Các nhóm biến còn lại (KiotViet, Odoo, NAS, Gemini, Web Push…) chỉ cần khi bật
> tính năng tương ứng — để trống/`0` là tắt. Xem chú thích trong `.env.example`.

### 4. Migrate & chạy

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Truy cập:
- Portal: http://127.0.0.1:8000/
- Trang quản trị Django: http://127.0.0.1:8000/admin-panel/

### 5. (Tuỳ chọn) Seed dữ liệu demo

```powershell
python manage.py seed_demo_data          # nhân sự, phòng ban…
python manage.py seed_kho_npl_demo       # kho nguyên phụ liệu
```

---

## Chạy bằng Docker (giống production)

```powershell
copy .env.example .env      # chỉnh DJANGO_ENV=production, SECRET_KEY, mật khẩu DB…
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

- `docker-compose.yml` khởi tạo 2 service: `db` (postgres:15-alpine) và `web` (gunicorn).
- Bản có SSL dùng `docker-compose.ssl.yml`. Xem thêm `DEPLOY-NHANH.txt` và
  `docs/HUONG_DAN_AUTO_DEPLOY.md`.

---

## Kiểm thử

```powershell
python manage.py test               # toàn bộ
python manage.py test hrm audit     # theo app
```

Nhiều app đã có test (`hrm`, `audit`, `tasks`, `service_requests`, `equipment`,
`nas_storage`, `kiotviet`…). Xem trạng thái coverage trong `docs/ARCHITECTURE.md`.

---

## Cấu trúc thư mục (rút gọn)

```
PortalJustPlay/
├── PortalJustPlay/       # settings, urls, wsgi, pwa, ckeditor
├── manage.py
├── <app>/                # ~20 app nghiệp vụ (models, views, urls, templates, tests)
│   └── management/commands/   # lệnh seed / đồng bộ / cron
├── docs/                 # tài liệu (kiến trúc, tích hợp, deploy)
├── scripts/              # script hạ tầng (ssl, backup, cron, relay…)
├── docker-compose.yml    # + docker-compose.ssl.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Lệnh quản trị hay dùng

| Lệnh                                         | Mục đích                                  |
|----------------------------------------------|-------------------------------------------|
| `python manage.py generate_recurring_tasks`  | Sinh công việc lặp lại (cron)             |
| `python manage.py kiotviet_sync`             | Đồng bộ dữ liệu KiotViet                  |
| `python manage.py sync_odoo_users`           | Đồng bộ tài khoản Portal → Odoo           |
| `python manage.py backup_to_nas`             | Sao lưu lên NAS (cron 00:00)              |
| `python manage.py send_meal_push_reminders`  | Nhắc đặt cơm qua Web Push                 |
| `python manage.py cleanup_orphan_media`      | Dọn file media không còn tham chiếu       |
| `python manage.py cleanup_activity_logs`     | Xóa nhật ký thao tác cũ hơn 7 ngày        |

Xem đầy đủ trong các thư mục `*/management/commands/`.
