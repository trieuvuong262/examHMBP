---
name: PortalJustPlay Project Context
alwaysApply: true
---

# Bối cảnh dự án PortalJustPlay

Bạn là trợ lý lập trình làm việc trên dự án **PortalJustPlay** — một hệ thống portal nội bộ xây bằng **Django** (Python), gồm nhiều app nghiệp vụ (hrm, surveys, recruitment, kho_npl, kho_san_pham, san_xuat, kpi, assessment, training, v.v.).

## Quy tắc bắt buộc trước khi làm việc

1. **Đọc `RULE.md` ở gốc dự án trước tiên.** Đây là entry point chính thức, nó dẫn tới:
   - `AI_AGENT_RULES.md` — chính sách chi tiết (minh bạch, approval gate, graph-first workflow, ngân sách ngữ cảnh, validation).
   - `docs/AI_CODEBASE_MAP.md` — kiến trúc hiện tại, registry module/workflow, entry points.
   - `docs/AI_CHANGELOG.md` — thay đổi gần đây khi task đụng vùng đã có tài liệu.

2. **Nêu plan trước khi hành động** (trước khi đọc source, sửa file, chạy lệnh):
   ```
   Plan: <sẽ làm gì>
   Why: <lý do/bằng chứng>
   Scope: <file/tool/lệnh>
   Expected: <kết quả/cách kiểm chứng>
   ```

3. **Approval gate — dừng và hỏi người dùng trước khi code** nếu: >10 file bị ảnh hưởng; cần quyết định đúng/sai hoặc chọn hướng triển khai khác nhau; thay đổi workflow nghiệp vụ; đụng tới bảo mật/quyền/credentials/dữ liệu; đổi hành vi của tính năng hiện có.

## Graph-first workflow (cách hiểu project mà không đọc hết 254k dòng)

- Dự án có **CodeGraph** (`.codegraph/`) để truy vấn cấu trúc (hàm gọi hàm nào, model nào liên quan).
- Giữ ngữ cảnh hẹp: tra cứu có chọn lọc rồi chỉ đọc đúng đoạn source cần thiết, KHÔNG đọc tràn lan.
- Dùng `@codebase` trong Continue để tìm các đoạn liên quan trước khi trả lời.

## Convention kỹ thuật

- `cwd` cho lệnh Django/CLI là `d:\Project\PortalJustPlay` (KHÔNG phải `d:\Project`).
- Lệnh thường dùng: `python manage.py ...` (migrate, test, runserver), chạy trong venv `.venv`.
- Code và giao tiếp bằng **tiếng Việt** khi có thể.
- Tuân thủ an toàn: thao tác phá hủy diện rộng hoặc ảnh hưởng production thì nêu rõ rủi ro trước khi làm.

## Khi hoàn thành

Báo cáo: các file đã đụng, ngữ cảnh graph/index đã dùng, các bước kiểm tra đã chạy, và giới hạn còn lại.
