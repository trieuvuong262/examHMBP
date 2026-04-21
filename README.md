# HỆ THỐNG QUẢN TRỊ NHÂN SỰ & ĐÀO TẠO NỘI BỘ (HRMS & LMS)

Hệ thống cung cấp giải pháp chuyển đổi số toàn diện cho vòng đời nhân sự, từ khâu tuyển dụng, quản lý hồ sơ, đào tạo trực tuyến đến đánh giá năng lực và theo dõi KPI.

---

## 1. CÔNG NGHỆ SỬ DỤNG (Tech Stack)

* **Backend:** Python 3.13.12, Framework Django
* **Database:** PostgreSQL (Version 12+) - Kết nối qua thư viện `psycopg2-binary`
* **Web Server (Production):** Waitress (WSGI) kết hợp NSSM (chạy Windows Service)
* **Frontend:** HTML5, CSS3, Bootstrap 5, Javascript, jQuery
* **Xử lý dữ liệu:** Thư viện `pandas`, `openpyxl` (Hỗ trợ Import/Export Excel quy mô lớn)

---

## 2. CÁC PHÂN HỆ CHỨC NĂNG CHÍNH

1.  **Tuyển dụng:** Quản lý quy trình ứng viên, chuyển đổi hồ sơ trúng tuyển thành nhân viên chính thức chỉ với 01 click.
2.  **Quản trị Nhân sự (Core HR):** Quản lý thông tin hồ sơ, sơ đồ tổ chức, phòng ban. Hỗ trợ cập nhật dữ liệu hàng loạt qua Excel.
3.  **Đào tạo nội bộ (LMS):** Số hóa bài giảng Video/PDF/Reading. Tự động gán lộ trình đào tạo theo chức danh/vị trí.
4.  **Đánh giá & Kiểm tra:** Hệ thống thi trắc nghiệm trực tuyến, tự động trộn đề, giới hạn thời gian và chấm điểm tức thì.

*-- Phân hệ đang phát triển --*
5.  **Quản lý KPI:** Thiết lập và đánh giá chỉ tiêu công việc định kỳ.
6.  **Báo cáo (Dashboard):** Hệ thống biểu đồ trực quan hóa biến động nhân sự và kết quả đào tạo.

---

## 3. HƯỚNG DẪN CÀI ĐẶT VÀ TRIỂN KHAI (DÀNH CHO IT)

### Bước 3.1: Chuẩn bị môi trường
1.  Cài đặt **Python 3.13.12** (Lưu ý tích chọn "Add Python to PATH").
2.  Cài đặt **PostgreSQL** và trình quản lý **pgAdmin 4**.
3.  Tạo một Database trống trên PostgreSQL với tên: `hrms_db`

### Bước 3.2: Khởi tạo ứng dụng
```bash
# 1. Tạo và kích hoạt môi trường ảo (Virtual Environment)
python -m venv venv
venv\Scripts\activate

# 2. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# 3. Import dữ liệu cấu trúc và dữ liệu mẫu vào PostgreSQL
# Thực hiện lệnh trong CMD tại thư mục gốc của dự án
psql -U postgres -d hrms_db < HRMS_Backup_21042026.sql
```
> **Lưu ý:** Cấu hình kết nối Database (User/Password) nằm trong file `.env`.

### 4. Phân quyền & Tài khoản truy cập

Hệ thống được phân cấp quyền truy cập chặt chẽ theo 3 đối tượng:

| Đối tượng | Link truy cập | Tài khoản mẫu | Quyền hạn |
| :--- | :--- | :--- | :--- |
| **Nhân viên (User)** | `http://ip` | `ltv002-bp` / `Hoanmy@123` | Xem bài giảng, thực hiện bài thi được giao. Menu quản trị bị khóa. |
| **Quản trị HR (Admin)** | `http://ip/dashboard` | `admin` / `123123` | Quản lý tuyển dụng, hồ sơ nhân sự, tạo khóa học và xem báo cáo. |
| **Kỹ thuật (IT)** | `http://ip/admin` | `admin` / `123123` | Can thiệp dữ liệu gốc, phân quyền chi tiết cho nhóm nhân sự (HR). |

---

## 5. TRIỂN KHAI VẬN HÀNH (PRODUCTION)

Để hệ thống chạy ổn định trên Windows Server dưới dạng dịch vụ ngầm:
1.  Sử dụng **Waitress** làm WSGI Server: 
    `waitress-serve --listen=0.0.0.0:80 hmc_hrms.wsgi:application`
2.  Sử dụng công cụ **NSSM** để đăng ký lệnh khởi chạy dự án thành một **Windows Service**.
3.  Cấu hình Firewall cho phép truy cập qua cổng 80 (hoặc cổng chỉ định).

---
**Người chịu trách nhiệm:** Vương - Bộ phận IT/HR
**Ngày cập nhật:** 21/04/2026