# 🏢 HỆ THỐNG QUẢN TRỊ NHÂN SỰ & ĐÀO TẠO NỘI BỘ (HRMS & LMS)

Hệ thống cung cấp giải pháp chuyển đổi số toàn diện cho vòng đời nhân sự, từ khâu tuyển dụng, quản lý hồ sơ, đào tạo trực tuyến đến đánh giá năng lực và theo dõi KPI.

---

## 🛠️ 1. CÔNG NGHỆ SỬ DỤNG (Tech Stack)

* **Backend:** Python 3.13.12, Framework Django
* **Database:** PostgreSQL (Version 12+) - Kết nối qua thư viện `psycopg2-binary`
* **Web Server (Production):** Waitress (WSGI) kết hợp NSSM (chạy Windows Service)
* **Frontend:** HTML5, CSS3, Bootstrap 5, Javascript, jQuery
* **Xử lý dữ liệu:** Thư viện `pandas`, `openpyxl` (Import/Export Excel nội bộ)

---

## 📦 2. CÁC PHÂN HỆ CHỨC NĂNG CHÍNH

1. **Tuyển dụng:** Quản lý vòng đời ứng viên, chuyển ứng viên trúng tuyển thành nhân viên chỉ với 1 click.
2. **Quản lý Nhân sự (Core HR):** Quản lý hồ sơ, phòng ban. Import/Export hàng loạt qua Excel.
3. **Đào tạo nội bộ (LMS):** Khóa học Video/PDF/Slide. Tự động gán lộ trình học theo chức danh. Thuật toán nhúng video an toàn.
4. **Đánh giá & Kiểm tra:** Thi trắc nghiệm trực tuyến, tự động trộn đề và chấm điểm.
5. **Quản lý KPI:** Thiết lập, đánh giá chỉ tiêu công việc định kỳ.
6. **Báo cáo (Dashboard):** Biểu đồ trực quan hóa dữ liệu theo thời gian thực.

---

## 🚀 3. HƯỚNG DẪN CÀI ĐẶT VÀ TRIỂN KHAI (DÀNH CHO IT)

### Bước 3.1: Chuẩn bị môi trường
1. Cài đặt Python 3.13.12  và thêm vào PATH.
2. Cài đặt **PostgreSQL** (Kèm theo pgAdmin để dễ quản lý nếu cần).
3. Tạo Database mới  `hrms_db`

### Bước 3.2: Cài đặt ứng dụng
```bash
# 1. Tạo và kích hoạt môi trường ảo
python -m venv venv
venv\Scripts\activate

# 2. Cài đặt thư viện
pip install -r requirements.txt


# 3. Import database demo vào pdAdmin
psql -U postgres -d hrms_db < HRMS_Backup_21042026.sql (trong source)
---- Lưu ý: mật khẩu db trong file .env ----

#4. Quy trình web
User thường truy cập váo link http://ip
    Account test là Username: ltv002-bp, Password: Hoanmy@123
    Sẽ chỉ truy cập được màn hình có các khóa đào tạo và khóa học được set sẳn
    Các menu sẽ bị khóa lại

Admin (Nhân viên HR) truy cập link http://ip/dashboard
    Account admin là Username: admin, Password: 123123
    Truy cập được tất cả chức năng


IT (IT) http://ip/admin
    Account admin là Username: admin, Password: 123123
    có thể set quyền cho nhân viên HR
