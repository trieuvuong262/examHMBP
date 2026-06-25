# Odoo 18 — Maintenance (Bảo trì)

> Nguồn: [Odoo 18 Maintenance documentation](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance.html)  
> Mục đích: tham chiếu thiết bị, work center, lịch bảo trì — liên kết MRP tại JustPlay.

---

## 1. Vai trò module

Maintenance giúp **theo dõi thiết bị** và **lên lịch bảo trì**:

- **Corrective** — sửa khi hỏng
- **Preventive** — bảo trì định kỳ tránh hỏng
- Gắn **Equipment** hoặc **Work Center** (ảnh hưởng sản xuất)
- Metrics: MTBF, MTTR, next failure estimate

**Không thay thế** CMMS đầy đủ nhưng đủ cho xưởng gắn với Odoo MRP.

---

## 2. Cây tài liệu Odoo 18 (Maintenance)

- Add new equipment
- **Maintenance calendar**
- **Maintenance requests**
- **Maintenance setup** (teams, categories, equipment, work centers)

---

## 3. Cấu trúc tổ chức

### 3.1 Maintenance teams
**Menu:** Maintenance → Configuration → Maintenance Teams

- Team name, **Team Members** (technicians)
- Company (multi-company)
- Technician = user được gán request

### 3.2 Equipment categories
**Menu:** Maintenance → Configuration → Equipment Categories

- Category Name, Responsible
- Email alias (tạo request qua email)
- Smart buttons: Equipment, Maintenance history

### 3.3 Machines & Tools (Equipment)
**Menu:** Maintenance → Equipment → Machines & Tools

| Field | Ý nghĩa |
|-------|---------|
| **Name** | Tên thiết bị |
| **Equipment Category** | Nhóm |
| **Used By** | Department / Employee / Other |
| **Maintenance Team** | Đội phụ trách |
| **Technician** | Người phụ trách cụ thể |
| **Used in location** | Vị trí (không phải WC) |
| **Work Center** | WC trong MRP dùng thiết bị này |

#### Tab Product Information
- Vendor, Model, Serial Number
- **Effective Date** — ngày đưa vào sử dụng (tính MTBF)
- Cost, Warranty Expiration

#### Tab Maintenance (metrics)
| Metric | Mô tả |
|--------|--------|
| **Expected MTBF** | Ngày giữa các lần hỏng (kỳ vọng) — **nhập tay** |
| **Mean Time Between Failure** | TB thực tế — **tự tính** từ corrective done |
| **Estimated Next Failure** | Latest Failure + MTBF |
| **Latest Failure** | Từ maintenance request gần nhất |
| **Mean Time To Repair** | TB ngày sửa — từ duration requests |

---

## 4. Work centers & equipment

**Menu:** Maintenance → Equipment → Work Centers

- Tab **Equipment** — list máy gắn WC
- Columns: Name, Technician, Category, MTBF, MTTR, Est. Next Failure
- **Add a line** — gán thiết bị vào WC

**Liên kết MRP:** Work Center trong Manufacturing = nơi chạy operations; block WC khi bảo trì → không lên lịch MO/WO.

---

## 5. Maintenance requests

**Doc:** [Maintenance requests](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/maintenance_requests.html)

**Menu:** Maintenance → Maintenance → Maintenance Requests

### Tạo request (New)

| Field | Ý nghĩa |
|-------|---------|
| **Request** | Tiêu đề |
| **For** | Equipment **hoặc** Work Center |
| **Equipment / Work Center** | Đối tượng |
| **Worksheet Template** | Form tuỳ chỉnh (nếu bật setting) |
| **Request Date** | Ngày tạo (auto, không sửa) |
| **Maintenance Type** | **Corrective** / **Preventive** |
| **Manufacturing Order** | MO liên quan (nếu hỏng khi SX) |
| **Work Order** | WO cụ thể |
| **Team / Responsible** | Đội / kỹ thuật viên |
| **Scheduled Date** | Lịch thực hiện |
| **Duration** | Thời gian sửa (00:00) |
| **Block Workcenter** | **Chặn** lập lịch WO/MO khác tại WC |
| **Priority** | 0–3 sao |

#### Notes & Instructions
- PDF upload / Google Slide link / Text hướng dẫn sửa

### Kanban stages
- New Request → … → **Repaired** (thành công)
- **Scrap** — thiết bị/WC không sửa được, thanh lý

Kéo thả hoặc đổi stage trên form.

---

## 6. Maintenance calendar

**Doc:** [Maintenance calendar](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/maintenance_calendar.html)

**Menu:** Maintenance → Maintenance → Maintenance Calendar

### Tạo từ calendar
- Click ô giờ → New Event → Create (nhanh) hoặc **Edit** (form đầy đủ)

### Views
Calendar (default), Kanban, List, Pivot, Graph, Activity

### Filters
- To Do, Active (mặc định)
- Save search → Favorite / Default / Shared

### Calendar sidebar
- Mini calendar
- **Technician list** — ai có request mở

### Kanban stage options (gear)
- **Request Confirmed** + Work Center: khi tick → **block work center** theo duration
- **Request Done** — stage cuối, đóng request

---

## 7. Luồng nghiệp vụ điển hình

### Corrective (máy hỏng giữa ca)
1. Công nhân / tổ trưởng tạo request Corrective
2. Gắn Equipment hoặc Work Center + MO/WO nếu có
3. Bật **Block Workcenter** nếu cần dừng chuyền
4. Team sửa → stage **Repaired** hoặc **Scrap**
5. MTBF/MTTR cập nhật trên equipment

### Preventive (bảo trì định kỳ)
1. Lên lịch trên **Maintenance Calendar** — type Preventive
2. Nhắc technician theo Scheduled Date
3. Hoàn thành → Repaired

### Tích hợp Shop Floor / MRP
- Tablet Shop Floor có thể trigger maintenance (doc MRP đề cập feedback loops)
- Block WC → MO mới không xếp vào WC trong khung giờ bảo trì

---

## 8. So sánh với Portal Equipment

| | Odoo Maintenance | Portal Equipment |
|--|------------------|------------------|
| Đối tượng | Máy SX / WC | IT, tài sản văn phòng, … |
| Mục tiêu | MTBF, downtime xưởng | IT helpdesk, scan tài sản |
| Liên kết | MRP Work Center | `equipment` app riêng |

JustPlay: **Odoo Maintenance** cho máy xưởng pilot; Portal Equipment cho IT/HR assets — không trộn một module.

---

## 9. Checklist thiết kế JustPlay

### Master data
- [ ] Equipment categories (CNC, ép, băng tải, …)
- [ ] Map equipment ↔ **Work Center** MRP
- [ ] Maintenance teams (cơ điện, bảo trì xưởng)

### Quy trình
- [ ] Ai tạo request? (ca SX vs bảo trì)
- [ ] Khi nào bật Block Workcenter?
- [ ] Preventive calendar theo giờ chạy máy hay calendar date?

### Metrics
- [ ] Expected MTBF nhập cho thiết bị quan trọng
- [ ] Review MTTR định kỳ

### Demo pilot
- **10 thiết bị**, **11 yêu cầu** `JP-DEMO-MR-*` — 4 máy gắn WC MRP
- Map: [pilot-demo-map.md §5](./pilot-demo-map.md#5-maintenance)
- Script: `seed_odoo_pilot_demo.py`, `seed_odoo_pilot_demo_expand.py`
- Mở rộng: gắn `manufacturing_order_id` khi hỏng máy giữa ca SX

---

## 10. Link doc ưu tiên

| Chủ đề | URL |
|--------|-----|
| Maintenance setup | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/maintenance_setup.html |
| Add equipment | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/add_new_equipment.html |
| Maintenance requests | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/maintenance_requests.html |
| Maintenance calendar | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/maintenance/maintenance_calendar.html |

---

## 11. Sơ đồ tích hợp (tóm tắt)

```text
Equipment ──gắn──► Work Center (MRP)
                        │
                        ▼
              Maintenance Request
              (Corrective / Preventive)
                        │
           Block Workcenter? ──► ẩn WC khỏi lịch SX
                        │
                        ▼
              Repaired / Scrap
                        │
                        ▼
              Cập nhật MTBF, MTTR trên Equipment
```
