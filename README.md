# 🏢 HỆ THỐNG QUẢN TRỊ NHÂN SỰ & ĐÀO TẠO NỘI BỘ (HRMS & LMS)

Hệ thống cung cấp giải pháp chuyển đổi số toàn diện cho vòng đời nhân sự, từ khâu tuyển dụng, quản lý hồ sơ, đào tạo trực tuyến đến đánh giá năng lực và theo dõi KPI.

---

## 🛠️ 1. CÔNG NGHỆ SỬ DỤNG (Tech Stack)

* **Backend:** Python 3.11, Framework Django
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
1. Cài đặt Python (3.10 trở lên) và thêm vào PATH.
2. Cài đặt **PostgreSQL** (Kèm theo pgAdmin để dễ quản lý nếu cần).
3. Tạo Database trống (Ví dụ: `hrms_db`).

### Bước 3.2: Cài đặt ứng dụng
```bash
# 1. Tạo và kích hoạt môi trường ảo
python -m venv venv
venv\Scripts\activate

# 2. Cài đặt thư viện
pip install -r requirements.txt