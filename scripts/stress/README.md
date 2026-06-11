# Stress test Portal JustPlay (k6)

Bộ kịch bản tải giả lập user đăng nhập và duyệt các module chính: **báo cáo**, **yêu cầu nội bộ**, **kho nguyên phụ liệu**.

## Cài k6 (Windows)

```powershell
winget install k6 --source winget
# hoặc: choco install k6
```

Kiểm tra: `k6 version`

## Cấu hình tài khoản test

```powershell
cd scripts\stress
copy stress.env.example stress.env
```

Sửa `stress.env`:

| Biến | Ý nghĩa |
|------|---------|
| `STRESS_BASE_URL` | `https://portal.justplay.vn` hoặc `http://127.0.0.1:8000` |
| `STRESS_USER` / `STRESS_PASS` | User test có quyền 4 module |
| `STRESS_VUS` | Số user ảo đồng thời (mặc định 10) |
| `STRESS_DURATION` | Thời gian giữ tải (mặc định `3m`) |
| `STRESS_RAMP` | Thời gian tăng/giảm VU (mặc định `30s`) |

**Lưu ý:** Tạo user test riêng trên Django admin; không dùng tài khoản thật. File `stress.env` không được commit.

## Chạy

Từ thư mục gốc project:

```cmd
.\stress-test.cmd
.\stress-test.cmd login
.\stress-test.cmd reports
.\stress-test.cmd requests
.\stress-test.cmd kho-npl
.\stress-test.cmd mixed
```

Hoặc trong `scripts\stress`:

```cmd
.\run.cmd mixed
```

Theo dõi VPS trong cửa sổ khác:

```cmd
.\monitor.cmd watch
```

## Kịch bản

| File | Mô tả |
|------|--------|
| `login.js` | Đăng nhập + trang chủ |
| `reports.js` | Báo cáo ngày/tuần, lịch sử, team |
| `requests.js` | Đề xuất & hỗ trợ — của tôi, theo dõi, chờ xử lý |
| `kho-npl.js` | Tổng quan, danh mục, tồn kho, phiếu, kiểm kê, báo cáo |
| `mixed.js` | Trộn ngẫu nhiên 3 module (mặc định) |

## Đọc kết quả

k6 in summary cuối run:

- **http_req_duration** — thời gian phản hồi (p95 quan trọng)
- **http_req_failed** — tỷ lệ lỗi HTTP
- **checks** — tỷ lệ assertion pass (login, trang 200/302)
- **vus** — số user ảo tại peak

### Ước lượng giới hạn thực tế

Portal chạy **Gunicorn 3 workers** → tối đa ~3 request Django nặng xử lý song song. Nếu p95 tăng mạnh hoặc `http_req_failed` > 5% khi `STRESS_VUS=10`, giảm VU hoặc tăng workers trên VPS.

### Tùy chỉnh nhanh (không sửa file)

```cmd
set STRESS_VUS=20
set STRESS_DURATION=5m
.\stress-test.cmd mixed
```

Hoặc truyền thẳng cho k6:

```cmd
cd scripts\stress
k6 run -e STRESS_VUS=15 -e STRESS_USER=... -e STRESS_PASS=... mixed.js
```

## Cấu trúc

```
scripts/stress/
  lib/auth.js          # Login Django + CSRF, helper GET
  login.js
  reports.js
  requests.js
  kho-npl.js
  mixed.js
  stress.env.example
  run.cmd / run.ps1
  README.md
```
