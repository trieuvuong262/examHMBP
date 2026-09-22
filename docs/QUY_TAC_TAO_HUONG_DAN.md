# Quy tắc tạo file hướng dẫn Portal

Dùng file này làm chuẩn mỗi khi viết/sửa hướng dẫn module (trang `/huong-dan/` hoặc PDF trong `docs/`).

Mẫu tham chiếu: `templates/guide/inner/cong-viec.html`, `templates/guide/inner/bao-cao.html`, `scripts/generate_cong_viec_guide_pdf.py`.

---

## 1. Đối tượng & giọng văn

- Người đọc là **nhân viên** và **quản lý** trên Portal, không phải lập trình viên.
- Viết tiếng Việt, câu ngắn, thao tác cụ thể: menu → tab → nút.
- Gọi vai trò: **Quản lý**, **Nhân viên**. Không ghi username, họ tên account demo, mật khẩu.
- Không có bước **Đăng nhập / Đăng xuất / chuyển user**. (Ngoại lệ: mục nền tảng «Đăng nhập», «Đổi mật khẩu».)
- Khi luồng đổi vai trò: tách section, không viết «đăng xuất A rồi đăng nhập B».

**Không**

- Quản lý: Vuonglnt — mật khẩu …
- Đăng nhập `long.tb` → …

**Có**

- Quản lý mở tab **Việc đã giao** → **+ Giao việc**.
- Nhân viên mở tab **Việc của tôi** → **Chi tiết**.

---

## 2. Khảo sát trước khi viết

1. Mở UI thật (ưu tiên `https://portal.justplay.vn`) đúng quyền từng vai trò.
2. Đối chiếu template/view trong repo — nút, tab, badge, trạng thái phải khớp UI, không bịa.
3. Ghi **đúng chữ trên nút** (`Nộp chờ duyệt`, không viết «nộp bài»).
4. Nếu pill lọc và badge khác chữ (vd. pill **Đang làm** / badge **Đang thực hiện**) thì ghi cả hai.

Không mô tả tính năng không có trên màn (vd. kéo-thả Kanban khi UI là bảng + Chi tiết).

---

## 3. Cấu trúc nội dung

Thứ tự cố định:

1. **Mở đầu** (1–3 câu): menu vào module, phạm vi (vd. chỉ Giao việc cá nhân, không gồm Dự án).
2. **Hộp demo** (nếu có chạy demo): việc / hạn / kết quả. Cấm tài khoản và mật khẩu.
3. **Nhân viên** — badge `bg-secondary` — bước làm việc hàng ngày.
4. **Quản lý** — badge `bg-primary` — chỉ phần quản lý mới thấy (giao, duyệt, cấu hình).
5. **Tóm tắt nút** (tip cuối): luồng nút một dòng.

Nếu module có nhiều «cảnh» (tạo → nhận → duyệt), lặp badge: Quản lý tạo → Nhân viên làm → Quản lý duyệt.

Bước đánh số liên tục **1, 2, 3…** xuyên suốt tài liệu (không reset về 1 khi đổi vai trò).

Mỗi bước:

- Vào màn nào (menu / tab / URL nếu cần).
- Điền / bấm gì.
- Kết quả thấy được (banner, badge trạng thái).
- Liệt kê **mọi nút trên màn đó** — kể cả nút không dùng trong demo, ghi rõ «không dùng trong demo».

---

## 4. File HTML trên Portal

| Việc | Nơi lưu |
|---|---|
| Nội dung mục | `templates/guide/inner/{section-id}.html` |
| Đăng ký mục lục / quyền | `hrm/guide_sections.py` (`GUIDE_SECTIONS`) |
| Map URL chụp ảnh bước | `hrm/guide_step_shots.py` |
| Ảnh | `static/images/guide/` |

`section-id` khớp `id` trong `GUIDE_SECTIONS` (vd. `cong-viec`, `bao-cao`).

Khối bước minh họa:

```html
<span class="badge bg-secondary mb-3">Nhân viên — …</span>
<div class="guide-steps mb-4">
    <div class="guide-step guide-step--illustrated">
        <div class="guide-step-head">
            <div class="guide-step-num">1</div>
            <div class="guide-step-body"><div>…</div></div>
        </div>
        <figure class="guide-step-figure">
            <img src="{% static 'images/guide/{section}-01.png' %}" alt="…" class="guide-zoomable" loading="lazy">
        </figure>
    </div>
</div>
```

- File HTML bắt đầu `{% load static %}`.
- Tên nút/tab bọc `<strong>`.
- Một bước có thể có nhiều `<figure>` nếu cần 2 màn (form + danh sách sau khi gửi).
- Ảnh: `class="guide-zoomable"`.

Hộp demo / tóm tắt: `div.guide-tip`.

---

## 5. Ảnh chụp màn hình

- Chụp **UI production** (hoặc staging giống production), không mock.
- Đi hết luồng demo trên hệ thống rồi chụp từng màn (tạo → nhận → làm → duyệt).
- Viewport đủ cao để **một khung** chứa hết nội dung + sidebar; **không** `full_page` khi header/sidebar sticky (ảnh bị đè / ghép lệch).
- Cắt khoảng trắng dư dưới nội dung; giữ sidebar + header để nhận ra menu.
- Không chụp form đăng nhập vào hướng dẫn module (trừ mục Đăng nhập).
- Tên file:
  - Chuẩn sổ tay: `{section-id}-{nn}.png` (vd. `bao-cao-01.png`) — khớp `guide_step_shots.py`.
  - Luồng dài: tên mô tả được (`cong-viec-form-filled.png`) rồi copy alias `{section}-{nn}.png` nếu mục HTML còn dùng số.

Script chụp sẵn: `scripts/capture_guide_screenshots.py` (cần `GUIDE_CAPTURE_USER` / `GUIDE_CAPTURE_PASSWORD` — **không** đưa mật khẩu vào tài liệu).

---

## 6. File PDF (tuỳ chọn)

- Thư mục: `docs/Huong_dan_{Ten_muc}.pdf`.
- Generator: `scripts/generate_{ten}_guide_pdf.py` (mẫu: `generate_cong_viec_guide_pdf.py`).
- Font Arial/DejaVu, A4, màu thương hiệu đỏ `#dc2626`.
- Cùng quy tắc vai trò / không tài khoản / không bước login.
- Gắn ảnh từ `static/images/guide/`; thiếu file thì bỏ ảnh, không vỡ PDF.
- Mục lục: bản đồ tab/trạng thái → nhân viên → quản lý → bảng nút → checklist.

Chạy:

```bash
python scripts/generate_cong_viec_guide_pdf.py
```

---

## 7. Bảng nút

Mỗi màn hình có bảng (PDF) hoặc list (HTML):

| Nút / ô | Việc làm | Dùng trong demo? |
|---|---|---|
| Giao việc | Tạo việc | Có |
| Hủy | Thoát form, không tạo | Không |
| Từ chối | Nhân viên không nhận | Không |

Nút nguy hiểm (**Hủy công việc**, **Yêu cầu sửa lại**) phải có mặt và ghi điều kiện.

---

## 8. Demo trên hệ thống

- Được tạo dữ liệu thật (VPS) để chụp, nhưng **tài liệu** chỉ nói việc / hạn / kết quả.
- Demo một lần, hạn rõ ngày, có trạng thái cuối (Hoàn thành / Chờ duyệt…).
- Không tick «miễn duyệt» nếu hướng dẫn cần bước duyệt.
- Dọn bản demo cũ (huỷ) trước khi chụp lại cho danh sách sạch.

Hộp demo chỉ gồm:

- Việc: …
- Hạn: …
- Kết quả: …

---

## 9. Đồng bộ

Sửa hướng dẫn thì cập nhật **cả** HTML inner và PDF (nếu PDF đã có).

Trên server, nội dung `/huong-dan/` có thể bị ghi đè trong DB. Sau khi deploy, nếu mục không đổi: xóa override mục đó hoặc chạy sync nội dung mặc định.

---

## 10. Checklist trước khi giao tài liệu

- [ ] Khảo sát UI thật, chữ nút/trạng thái khớp
- [ ] Phân **Nhân viên** / **Quản lý**, không username/mật khẩu
- [ ] Không bước đăng nhập / chuyển user
- [ ] Đủ nút trên từng màn, kể cả nút không bấm trong demo
- [ ] Ảnh UI thật, không đè sidebar, đã cắt trắng
- [ ] HTML: `{% load static %}`, `guide-step--illustrated`, `guide-zoomable`
- [ ] `guide_sections.py` / `guide_step_shots.py` khớp `section-id` nếu mục mới
- [ ] PDF (nếu có) regenerate sau khi sửa chữ/ảnh
