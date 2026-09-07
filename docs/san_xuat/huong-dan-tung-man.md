# Hướng dẫn từng màn hình — Sản xuất Portal

Chỉ các màn **đang mở trên menu**. Mỗi mục: vào đâu → làm gì → nút nào → kết quả.

---

## 1. Hồ sơ

### 1.1 Hồ sơ thiết kế sản phẩm — danh sách

- **Menu:** Sản xuất → Hồ sơ → Hồ sơ thiết kế sản phẩm  
- **URL:** `/san-xuat/ho-so/`  
- **Tiêu đề:** Hồ sơ thiết kế sản phẩm

| Việc | Cách làm |
|------|----------|
| Tìm mã | Ô lọc trên lưới (mã / tên) |
| Mở hồ sơ | Bấm một dòng |
| Tạo mới | Nút **Thêm** (góc phải) |
| Xem BOM / quy trình nhanh | Cột liên kết BOM hoặc routing trên dòng |

### 1.2 Chi tiết hồ sơ

- **URL:** `/san-xuat/ho-so/<id>/`  
- Tab trên màn: **Thông tin · SKU · BOM · Quy trình · Costing · Thiết kế**

| Tab | Việc nhân viên cần biết |
|-----|-------------------------|
| Thông tin | Tên hàng, mùa, vải chính |
| SKU | Màu × size |
| BOM | Định mức NPL — bản đang dùng phải **kích hoạt** trước khi Chuyển SX |
| Quy trình | Công đoạn / routing IE. Bản duyệt mới dùng được trên đơn |
| Thiết kế | File ảnh / bản vẽ |

Trước khi lên đơn: kiểm tra tab **BOM** và **Quy trình** đã có bản dùng được.

### 1.3 Duyệt công đoạn / Thư viện / Năng lực

- **Duyệt công đoạn** `/san-xuat/cong-doan/duyet/` — IE duyệt SMV trước khi xác nhận đơn.  
- **Thư viện công đoạn** — danh mục chuẩn, không phải màn làm hàng ngày.  
- **Năng lực SX** — tải tổ / ngày; kế hoạch xem khi xếp Lộ trình.

---

## 2. Đơn đặt hàng

### 2.1 Danh sách đơn

- **Menu:** Sản xuất → Đơn đặt hàng → Danh sách đơn  
- **URL:** `/san-xuat/don-hang/`  
- **Nút:** **Lên đơn**

Cột: Số đơn · Khách · Ngày DK thực hiện · Ngày DK hoàn thành · Số dòng · SL · **Xác nhận** · **TT sản xuất**.

Lọc: tìm mã/khách + trạng thái xác nhận (Chưa / Đã xác nhận / Từ chối).  
Bấm dòng → chi tiết đơn.

### 2.2 Lên đơn đặt hàng / Sửa đơn

- **Menu:** Lên đơn đặt hàng · hoặc Sửa từ chi tiết (khi còn nháp)  
- **URL:** `/san-xuat/don-hang/them/`  
- **Nút lưu:** **Lưu đơn** (tạo mới) / **Lưu** (sửa)

**Phần đầu đơn:** khách hàng, ngày dự kiến thực hiện, ngày dự kiến hoàn thành, ghi chú.

**Bảng dòng hàng:**

1. Chọn **sản phẩm** (mã hồ sơ).  
2. Chọn **BOM**.  
3. Cột IE / routing — hệ thống gợi ý bản đã duyệt; chỉnh nếu cần.  
4. Nhập SL theo **size** (ô màu × size).  
5. Có thể thêm nhiều dòng.

Sau **Lưu đơn** → vào chi tiết, trạng thái còn **Nháp / chưa xác nhận**.

### 2.3 Chi tiết đơn

- **URL:** `/san-xuat/don-hang/<id>/`

| Nút | Khi nào | Kết quả |
|-----|---------|---------|
| **Xác nhận** | Đơn nháp, đủ công đoạn / SMV | Vào hàng đợi kế hoạch |
| **Từ chối** | Đơn nháp | Không SX; nhập lý do nếu hỏi |
| Link **Kế hoạch sản xuất** | Đã xác nhận | Mở board, lọc theo mã đơn |

Sau xác nhận: không sửa routing/SMV trên đơn.

### 2.4 Xác nhận đơn đặt hàng (hàng đợi duyệt)

- **Menu:** Đơn đặt hàng → Xác nhận đơn đặt hàng  
- **URL:** `/san-xuat/don-hang/xac-nhan/`  
- Chỉ hiện đơn **chưa xác nhận**.

Trên mỗi dòng: **Xác nhận** hoặc **Từ chối** (+ ô lý do). Có thể mở mã đơn để xem BOM/quy trình trước khi duyệt.

---

## 3. Kế hoạch SX

### 3.1 Kế hoạch sản xuất — tab Hàng đợi

- **Menu:** Kế hoạch SX → Kế hoạch sản xuất  
- **URL:** `/san-xuat/ke-hoach/bang/?tab=queue`  
- Tab: **Hàng đợi · Đã chuyển SX · Lộ trình**

Đơn đã xác nhận, chưa chuyển SX (hoặc đang tạm giữ).

| Nút / chỗ | Việc |
|-----------|------|
| Ô tìm | Mã đơn / khách |
| Ưu tiên | Đổi mức trên dòng (1–5) |
| **Giữ** | Tạm giữ — không Chuyển SX |
| **Bỏ giữ** | Đưa lại hàng đợi |
| **Chuyển SX** | Mở modal **Chuyển SX — BOM & công đoạn** |

**Trong modal Chuyển SX:**

1. Mỗi mã SP trên đơn: chọn BOM (bắt buộc) và routing nếu có nhiều bản.  
2. Nếu thiếu hồ sơ: link **Tạo hồ sơ thiết kế**, rồi mở lại modal.  
3. Bấm **Chuyển SX** → sinh lệnh, tự phát hành, đẩy **Phân công SX**.

### 3.2 Tab Đã chuyển SX

- **URL:** `?tab=released`  
- Lọc khoảng ngày (mặc định theo kỳ).

| Nút | Việc |
|-----|------|
| **Tiến độ** | Phiếu tiến độ theo đơn |
| Hủy chuyển SX | Chỉ khi chưa có xuất VT / thống kê / nhập TP / bàn giao / đang SX |

### 3.3 Tab Lộ trình

- **URL:** `?tab=route`  
- Thanh thời gian theo **tổ**. Kéo để đổi ngày bắt đầu tổ.  
- Phút kiểm đếm / vận chuyển giữa tổ: dấu **+** trên mũi tên (hoặc màn Thời gian trung gian).

### 3.4 Thời gian trung gian

- **Menu:** Kế hoạch SX → Thời gian trung gian  
- **URL:** `/san-xuat/ke-hoach/thoi-gian-trung-gian/`  

Nhập **phút kiểm đếm** và **phút vận chuyển** giữa cặp tổ (Cắt→In ép, …).  
**Lưu** ở cuối thẻ. Số này dùng khi tính Lộ trình.

### 3.5 Kế hoạch NPL (nhánh thiếu vải)

- **URL:** `/san-xuat/ke-hoach/npl/`  
- Nút danh sách: **Tính kế hoạch nguyên phụ liệu**

Trên chi tiết:

| Nút | Việc |
|-----|------|
| Làm mới tồn | Cập nhật thiếu / đủ theo Kho NPL |
| **Xác nhận kế hoạch nguyên phụ liệu** | Chốt bảng nhu cầu |
| **Tạo yêu cầu mua nguyên phụ liệu từ shortfall** | Sinh PR cho dòng thiếu |

### 3.6 Yêu cầu mua NPL

- **URL:** `/san-xuat/ke-hoach/yeu-cau-mua-npl/`  
- Tạo mới hoặc từ kế hoạch NPL.

Chi tiết: **Gửi duyệt** → người có quyền bấm **Duyệt yêu cầu mua** hoặc Từ chối.  
Sau duyệt: nhập hàng trên **Kho NPL**.

---

## 4. Kho NPL

Menu **Kho NPL** (cùng nhóm Sản xuất). Màn dùng hàng ngày với SX:

| Màn | Khi nào vào |
|-----|-------------|
| Tồn kho NPL | Kiểm trước Chuyển SX / xuất VT |
| Phiếu xuất | Sau khi **Duyệt xuất** trên Yêu cầu xuất vật tư |
| Phiếu nhập | Hàng mua về từ yêu cầu mua NPL |

Không tạo phiếu xuất tay thay cho YCX nếu lệnh đã chạy trên Portal — duyệt YCX sẽ sinh phiếu.

---

## 5. Điều phối

### 5.1 Lệnh sản xuất — danh sách

- **Menu:** Điều phối → Lệnh sản xuất  
- **URL:** `/san-xuat/dieu-phoi/lenh-sx/`  
- Lệnh thường **đã có** sau Chuyển SX. Tạo tay chỉ khi làm lệnh ngoài đơn.

Bấm dòng → chi tiết. Tiêu đề thường là **mã đơn**; phụ đề **LSX …**.

### 5.2 Chi tiết lệnh

- **URL:** `/san-xuat/dieu-phoi/lenh-sx/<id>/`

**Thanh công cụ:** In A5 · Tiến độ · Truy vết · Quay lại.

**Nút theo trạng thái:**

| Trạng thái lệnh | Nút chính |
|-----------------|-----------|
| Nháp | **Phát hành** (lệnh tạo tay; lệnh từ Chuyển SX thường đã phát hành) · **Lưu** khi còn sửa |
| Đã phát hành / Đang SX | **Xuất VT** nếu chưa xuất · **Kiểm tra sản phẩm** nếu QC chưa xong · tạo **Nhập TP** khi QC xong |
| Đủ điều kiện | **Hoàn thành** (checklist 100%) |

Các khối trên trang: NVL / YCX, nhập TP, QC, bàn giao BTP — mỗi khối có nút **Tạo** nếu chưa có chứng từ.

### 5.3 Yêu cầu xuất vật tư

- **Menu:** Điều phối → Yêu cầu xuất vật tư  
- Hoặc từ lệnh: nút **Xuất VT** / **Tạo**

**Chi tiết YCX** `/dieu-phoi/yeu-cau-xuat-vt/<id>/`:

| Nút | Việc |
|-----|------|
| **Duyệt xuất đủ** | Xuất hết SL yêu cầu → phiếu xuất Kho NPL ghi sổ |
| **Duyệt xuất một phần** / **Bổ sung xuất đủ** | Xuất thiếu, sau đó xuất nốt |
| **In A5** | Phiếu giấy ra kho |

Kiểm vị trí kho trên từng dòng trước khi duyệt.

### 5.4 Tình hình bàn giao

- **Menu:** Điều phối → Tình hình bàn giao  
- **URL:** `/san-xuat/dieu-phoi/tinh-hinh-ban-giao/`  

Bảng theo lệnh / công đoạn: đã gửi, đã nhận, còn treo.  
Tạo phiếu bàn giao từ chi tiết lệnh (khối bàn giao → **Tạo**) hoặc `/dieu-phoi/ban-giao-btp/them/`.  
Người nhận: xác nhận hoặc từ chối trên phiếu.

### 5.5 Yêu cầu nhập thành phẩm

- **Menu:** Điều phối → Yêu cầu nhập thành phẩm  
- Nút: **Tạo yêu cầu nhập thành phẩm** (hoặc từ lệnh khi QC xong)

Màn **Nhập thành phẩm:**

1. Chọn lệnh / đơn.  
2. Nhập SL theo size, chọn **kho** nhận (có thể tách cùng size sang 2 kho).  
3. **Tiếp tục** nếu nhập một phần; nút nhận đủ khi nhập hết.  

Sau nhận: kiểm **Kho sản phẩm**.

---

## 6. Phân công SX

Thanh trên mỗi tổ: **Công việc · Quản lý nhân sự · Tiến độ hàng hoá**.

### 6.1 Tiến độ hàng hoá

- **Menu:** Phân công SX → Tiến độ hàng hoá  
- **URL:** `/san-xuat/cong-viec-to/tien-do-hang-hoa/`  
- **Tiêu đề:** Tiến độ hàng hoá  

Lưới mọi lệnh × mọi tổ. Lọc ưu tiên / hạn / trạng thái.  
Dùng để tổ trưởng biết đơn gấp — **không** ghi sản lượng ở đây. Bấm vào lệnh/tổ để sang board tổ.

### 6.2 Quản lý tổ (board) — Cắt / In ép / Thêu / May / Ủi / Giao hàng

- **URL:** `/san-xuat/cong-viec-to/<cat|inep|theu|may|ht|gh>/`  
- **Tiêu đề:** Quản lý tổ …

Mỗi phiếu lệnh:

| Nút | Việc |
|-----|------|
| **Nhận sản xuất** | Lần đầu — KHSX / lệnh sang *Đang sản xuất* |
| **Phân công** (từng công đoạn) | Chọn nhân viên → **Lưu phân công** |
| Phiếu tiến độ | Mở bảng ghi SL theo ngày / công đoạn |
| **Hoàn thành** | Khóa tổ này trên lệnh |
| Mở lại | Chỉ khi đã hoàn thành và có quyền |

Lọc: tìm lệnh / SP / đơn. Có mục xem phiếu đã hoàn thành.

**Thuê gia công** (cùng nhóm menu): khi phiếu GC đang mở — không phân công nội bộ tổ đó; nhận hàng GC trên phiếu.

### 6.3 Tiến độ tổ (phiếu ghi SL)

- **URL:** `/san-xuat/cong-viec-to/<slug>/tien-do/<mo_id>/`  
- **Tiêu đề:** Tiến độ tổ · …

Bảng ngày × công đoạn. Gõ SL vào ô (lưu khi rời ô).  
Chưa **Nhận sản xuất** thì chưa ghi được.  
Người được phân công mới sửa ô của mình (trừ quản lý).

### 6.4 Quản lý nhân sự tổ

- **URL:** `/san-xuat/cong-viec-to/<slug>/nhan-su/`  
- Gán người vào tổ, hồ sơ năng lực — để danh sách **Phân công** có đủ người.

---

## 7. Kiểm tra chất lượng

### 7.1 Tiến độ QC

- **Menu:** Kiểm tra chất lượng → Tiến độ QC  
- **URL:** `/san-xuat/chat-luong/`  
- Lưới lệnh / tổ: đã kiểm chưa, Đạt / chưa. Bấm sang phiếu hoặc board tổ QC.

### 7.2 Phiếu kiểm tra

- **Menu:** Phiếu kiểm tra  
- **URL:** `/san-xuat/chat-luong/phieu/`  
- **Tạo phiếu** (hoặc từ lệnh / tiến độ QC)

**Chi tiết phiếu** — tab theo tổ (Cắt, In ép, …):

1. Nhập tiêu chí / SL đạt–lỗi trên **tab tổ đang mở**.  
2. **Lưu tổ …** từng tab.  
3. Khi đã lưu đủ tổ: **Chốt phiếu** (Đạt / Không đạt).  
4. **Hủy chốt** nếu cần sửa (có quyền).

Chưa chốt Đạt + còn cảnh báo mở → không nhập thành phẩm.

### 7.3 Cảnh báo chất lượng · Hàng không đạt

- **Cảnh báo:** `/san-xuat/chat-luong/canh-bao/` — xử lý / đóng trước nhập TP.  
- **Xử lý hàng không đạt (NCR):** `/san-xuat/ncr/` — phiếu hàng lỗi, quyết định sửa / hủy / giữ.

### 7.4 Tiêu chuẩn chất lượng

Danh mục (một lần): tiêu chí, bộ tiêu chuẩn, lỗi. Phiếu kiểm tra lấy từ đây. Không phải màn làm hàng ngày của tổ.

---

## 8. Kho sản phẩm

- **Menu:** Sản xuất → Kho sản phẩm  
- Sau **Yêu cầu nhập thành phẩm** đã nhận: xem **Tồn kho** / **Phiếu nhập**.  
- Không nhập tay trùng một lần nữa nếu đã nhận trên YCNTP.

---

## 9. Báo cáo

### 9.1 Truy xuất nguồn gốc

- **URL:** `/san-xuat/truy-xuat/`  
- Gõ mã **đơn / lệnh / lô / SKU**.  
- Timeline: đơn → Chuyển SX → xuất VT → tiến độ tổ → QC → nhập TP.

Từ chi tiết lệnh: nút **Truy vết**.

### 9.2 Báo cáo vận hành

- **URL:** `/san-xuat/bao-cao-van-hanh/`  
- KPI lệnh, sản lượng, QC theo kỳ. Chỉ xem, không tạo chứng từ.

---

## 10. Tổng quan

- **Menu:** Sản xuất → Tổng quan  
- **URL:** `/san-xuat/tong-quan/`  
- Tab: Tổng hợp · Lệnh sản xuất · Sản lượng · Chất lượng.  
- Lọc ngày / tháng. Bấm số liệu để nhảy sang màn liên quan. Không nhập liệu ở đây.

---

## 11. Quy ước chung trên lưới

Hầu hết danh sách (YCX, YCNTP, phiếu QC, kế hoạch NPL…):

- Bấm **dòng** để mở chi tiết.  
- Lọc ngày + ô tìm ở phía trên.  
- Nút xuất Excel (nếu có) trên thanh công cụ.  
- **In A5** chỉ trên chi tiết chứng từ (lệnh, YCX, phiếu QC, bàn giao…).

Quyền: không thấy nút = tài khoản chưa được cấp **Tạo / Sửa** trên menu đó (chỉ **Xem**).
