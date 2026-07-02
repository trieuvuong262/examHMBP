---
inclusion: always
---

# Quy tắc dùng CodeGraph để khám phá code

Dự án này có sẵn CodeGraph index (`.codegraph/codegraph.db`) và CLI `codegraph`.
Ưu tiên dùng CodeGraph để tiết kiệm credit/token thay vì đọc full file.

## Thứ tự ưu tiên khi cần hiểu code

1. **Ưu tiên CodeGraph trước** — dùng các lệnh sau (chạy tại thư mục gốc dự án):
   - `codegraph query <search>` — tìm symbol (class, function, method, route...)
   - `codegraph context <task>` — dựng ngữ cảnh cho một task (xuất markdown)
   - `codegraph callers <symbol>` — tìm nơi gọi đến symbol
   - `codegraph callees <symbol>` — tìm symbol mà một hàm gọi tới
   - `codegraph impact <symbol>` — phân tích ảnh hưởng khi đổi symbol
   - `codegraph files` — xem cấu trúc file từ index
   - `codegraph status` — xem trạng thái index

2. **Chỉ đọc full file khi**: đã thử xử lý một vấn đề qua CodeGraph **3 lần không thành công**,
   lúc đó mới đọc trực tiếp toàn bộ file liên quan.

## Giữ index luôn mới

- Sau khi chỉnh sửa nhiều file, chạy `codegraph sync` để cập nhật index.
- Nếu nghi ngờ index lỗi/cũ, chạy `codegraph sync` (hoặc `codegraph index` để index lại toàn bộ).

## Lưu ý khi chạy lệnh

- Chạy lệnh với `cwd` là `d:\Project\PortalJustPlay`.
- Các lệnh này chạy nhanh, không phải tiến trình nền.
