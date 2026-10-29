# AI Codebase Map — PortalJustPlay

Tài liệu ngắn dành cho AI agent. Đây là bản đồ định hướng, không thay thế source code. Khi có mâu thuẫn, source và graph index là nguồn chính xác hơn.

Bootstrap entry point dùng chung cho mọi vibe-coding tool nằm tại `RULE.md`; hãy đọc file đó trước khi làm việc. `RULE.md` sẽ điều hướng tới `AI_AGENT_RULES.md`, code map, changelog và rule theo client. `AGENTS.md` chỉ là pointer phụ để agent tự nhận diện bootstrap.

## Snapshot

- Framework: Django 5.2 + Django REST Framework.
- Python local hiện dùng virtualenv tại `.venv`; production chạy Docker/Gunicorn.
- Database: PostgreSQL.
- Background jobs: Redis + RQ/django-rq.
- Deployment: Docker Compose; service chính là `web`, `worker`, `migrate` và các service hạ tầng liên quan.
- MCP local: `codegraph` và `codebase-memory` được cấu hình trong `.cursor/mcp.json`.

## Entry points

- `manage.py`: Django management commands.
- `PortalJustPlay/settings.py`: settings, environment và database.
- `PortalJustPlay/urls.py`: root URL routing.
- `PortalJustPlay/wsgi.py`: WSGI entry point.
- `PortalJustPlay/asgi.py`: ASGI entry point.
- `<app>/urls.py`: route của từng domain app.
- `<app>/views.py` hoặc module views chuyên biệt: HTTP request flow.
- `<app>/models.py`: domain persistence.
- `<app>/management/commands/`: scheduled/admin operations.
- `<app>/tasks.py` hoặc RQ integration: background work.

## Domain apps chính

- `hrm`: nhân sự, tổ chức và nghiệp vụ nhân sự.
- `kho_npl`: kho nguyên phụ liệu.
- `kho_san_pham`: kho thành phẩm.
- `san_xuat`: nghiệp vụ sản xuất.
- `reports`: báo cáo.
- `audit`: audit, security và một số integration/admin flows.
- `documents`, `library`, `training`, `assessment`, `kpi`, `tien_do`: nội dung, đào tạo, đánh giá và tiến độ.
- `kiotviet`, `odoo`: tích hợp hệ thống ngoài.
- `nas_storage`: file/NAS và các luồng storage.
- `tasks`, `service_requests`, `equipment`, `announcements`, `feedback`: các domain hỗ trợ.

Danh sách app không đầy đủ; dùng CodeGraph/Codebase Memory để xác nhận symbol và dependency thực tế.

## Module registry

Cập nhật bảng này khi thêm, đổi tên hoặc xoá module/app/package. Chỉ ghi thông tin định hướng; source code là nguồn chi tiết.

| Module/app | Trách nhiệm | Entry points/symbols | Dependencies/integrations | Tests |
|---|---|---|---|---|
| `hrm` | Nhân sự, tổ chức và nghiệp vụ HR | `hrm/urls.py`, `hrm/views.py`, `hrm/models.py` | PostgreSQL, permissions, audit | `hrm/tests*` |
| `kho_npl` | Kho nguyên phụ liệu | `kho_npl/urls.py`, views/services/models | PostgreSQL, Odoo/NAS khi liên quan | `kho_npl/tests*` |
| `kho_san_pham` | Kho thành phẩm | `kho_san_pham/urls.py`, views/models | PostgreSQL | `kho_san_pham/tests*` |
| `san_xuat` | Kế hoạch và nghiệp vụ sản xuất | `san_xuat/urls.py`, views/services | HRM, kho, PostgreSQL | `san_xuat/tests*` |
| `reports` | Báo cáo và export | `reports/urls.py`, views/services | PostgreSQL, RQ cho tác vụ nặng | `reports/tests*` |
| `audit` | Audit, bảo mật và admin flows | `audit/urls.py`, views/services | PostgreSQL, Odoo/NAS tùy flow | `audit/tests*` |
| `kiotviet`, `odoo` | Tích hợp hệ thống ngoài | app `urls.py`, services/management commands | API/XML-RPC, credentials qua environment | app tests |
| `nas_storage` | File và NAS | `nas_storage/urls.py`, services | Synology/rclone/LDAP | `nas_storage/tests*` |

Khi thêm module, không chỉ thêm một dòng tên: ghi rõ trách nhiệm, entry point, dependency và test. Nếu bảng trở nên quá dài, tách registry chuyên biệt nhưng giữ liên kết từ đây.

## Feature and workflow registry

Mỗi tính năng quan trọng nên có một dòng để agent biết bắt đầu trace từ đâu. Cập nhật khi route, flow hoặc owner thay đổi.

| Feature/workflow | Start here | Main path | Async/external | Verification |
|---|---|---|---|---|
| Portal request flow | `PortalJustPlay/urls.py` | root URL → app URL → view/API → service/model → response/template | tùy app | app tests |
| Background jobs | `<app>/tasks.py`, `*/management/commands/` | request/command → RQ → worker → result | Redis/RQ | task tests/logs |
| NPL inventory | `kho_npl/urls.py` | route → view → service/model → stock/ledger; tồn lưu theo ĐVT lẻ/base, Tồn chẵn quy đổi từ quy cách, Giá trị tồn = tồn base × đơn giá BQ gia quyền theo lô | Odoo/NAS nếu có | `kho_npl` tests |
| Production planning | `san_xuat/urls.py` | route → view → planning/service → HRM/kho; order detail BOM/OB is read-only by default, edit mode opens BOM material picker / OB operation-library picker → `order_routing.update_order_line_bom_overrides` / `sync_active_mos_from_order` → KHSX NPL + active LSX remainder | RQ nếu export/nặng | `san_xuat` tests |
| External sync | `kiotviet/`, `odoo/` | trigger/command → integration service → remote API | network/API | integration tests/logs |
| Recruitment Kanban | `recruitment/views.py::kanban_board` | Candidate status transition → `recruitment/services.py::transition` → Kanban column/audit event; `hired` may move to `joined_then_left` after the candidate has joined and left | PostgreSQL migration `recruitment/migrations/0031_candidate_joined_then_left.py` | `python manage.py check`, recruitment tests |

Khi cập nhật workflow, mô tả ngắn: trigger, các bước chính, dữ liệu thay đổi, async/external boundary, quyền và test. Không chép toàn bộ implementation vào Markdown.

## Agent transparency contract

Mọi AI agent phải công khai kế hoạch ngắn trước khi đọc, sửa, chạy lệnh, index dữ liệu hoặc thay đổi cấu hình. Kế hoạch tối thiểu gồm mục tiêu, lý do, phạm vi file/tool và kết quả dự kiến. Agent không cần tiết lộ chain-of-thought nội bộ; chỉ cần nêu kế hoạch, giả định, rủi ro và quyết định có thể kiểm chứng. Nếu kế hoạch thay đổi, phải thông báo trước khi thực hiện hướng mới.

### Approval gate

Agent phải dừng và hỏi người dùng trước khi code nếu có ít nhất một điều kiện:

- dự kiến tạo/cập nhật trên 10 file;
- cần quyết định đúng/sai hoặc chọn giữa các phương án triển khai đáng kể;
- thay đổi workflow;
- ảnh hưởng security, quyền, privacy, credentials, data exposure hoặc compliance;
- thay đổi policy, rule agent, MCP/indexing hoặc development workflow;
- thay đổi behavior, phạm vi, acceptance criteria hoặc user-facing contract của feature hiện có.

Khi gặp approval gate, agent chỉ được đọc context tối thiểu sau khi đã thông báo, rồi phải đưa plan, phạm vi, số file ước tính, phương án, rủi ro và câu hỏi lựa chọn. Chưa được code, migration, chỉnh config diện rộng hoặc thao tác phá huỷ trước khi người dùng trả lời. Nếu trong lúc làm phạm vi vượt 10 file hoặc phát sinh nhóm thay đổi được bảo vệ, phải dừng và hỏi lại.

## Documentation maintenance contract

`RULE.md` là bootstrap entry point; `AI_AGENT_RULES.md` là policy chi tiết; file này là bản đồ trạng thái hiện tại; `docs/AI_CHANGELOG.md` là lịch sử thay đổi. Khi code thay đổi, agent phải cập nhật tài liệu theo ma trận trong `AI_AGENT_RULES.md`. Mỗi entry phải trỏ đến source path hoặc symbol, không ghi secret/token thật.

## Quy tắc khám phá nhanh

1. Câu hỏi về route/view/function/class: dùng CodeGraph `context`, `search`, `trace`, `callers`, `callees` hoặc `impact` trước.
2. Không biết tên implementation hoặc cần liên hệ code với Docker/docs/config: dùng Codebase Memory semantic search/context.
3. Sau graph query chỉ mở source của symbol trực tiếp liên quan, ưu tiên line range.
4. Kiểm tra test tương ứng trong cùng app sau khi sửa.
5. Không index/đọc thường xuyên các dữ liệu local: `.env*`, `.venv`, `media`, `backups`, `.git`, `.codegraph`, build artifacts và dump tạm.

## Luồng triển khai điển hình

```text
browser/API -> root/app urls -> view/API view -> form/serializer/service
           -> model/query -> template/response
           -> RQ task/worker nếu tác vụ nặng
           -> external integration (Odoo/KiotViet/NAS) nếu có
```

Đây là sơ đồ định hướng. Với một task cụ thể, phải trace graph để lấy đường đi thật thay vì suy đoán theo sơ đồ.

## Kiểm tra sau thay đổi

```powershell
python manage.py check
python manage.py test --noinput --verbosity=1
python -m compileall -q <changed-python-files>
git diff --check
git status --short
```

Chỉ chạy test phạm vi hẹp trước nếu toàn bộ test mất nhiều thời gian; trước khi kết thúc task nên chạy test phù hợp với vùng đã sửa.
