# AI / Architecture Change Log — PortalJustPlay

Đây là lịch sử ngắn dành cho AI agent. Chỉ ghi thay đổi có ảnh hưởng đến module, feature, workflow, integration, kiến trúc, indexing hoặc policy agent. Không ghi mọi commit nhỏ và không ghi secret/token.

## Cách ghi

Mỗi entry nên có:

- **Date**: `YYYY-MM-DD`
- **Type**: `module | feature | workflow | integration | architecture | ai-policy | indexing`
- **Change**: đã thay đổi gì
- **Reason**: vì sao
- **Source**: file/module/symbol liên quan
- **Agent impact**: lần sau agent cần bắt đầu tra cứu ở đâu hoặc tránh hiểu sai điều gì

## Entries

### 2026-10-29 — feature / recruitment-kanban-label-and-sizing

- **Change**: Đổi nhãn trạng thái `joined_then_left` thành “Nhận việc nhưng nghỉ việc” và đồng nhất kích thước các cột Kanban.
- **Reason**: Nhãn ngắn gọn hơn và giao diện Kanban dễ so sánh giữa các cột.
- **Source**: `recruitment/models.py::Candidate`, `recruitment/views.py::KANBAN_COLUMNS`, `recruitment/templates/recruitment/admin/kanban_board.html`, migration `0032_rename_joined_then_left_label.py`.
- **Agent impact**: Mã trạng thái không đổi; chỉ thay đổi nhãn hiển thị và layout.

### 2026-10-29 — workflow / recruitment-candidate-joined-then-left

- **Change**: Thêm trạng thái ứng viên `joined_then_left` — “Ứng viên nhận việc xong rồi nghỉ việc” — vào model, Kanban và luồng chuyển trạng thái; chỉ cho phép chuyển từ `hired`, có audit event và không tính lại chỉ tiêu đang tuyển.
- **Reason**: Theo dõi riêng ứng viên đã nhận việc rồi nghỉ việc thay vì để lẫn với hồ sơ đã nhận việc hoặc không nhận việc.
- **Source**: `recruitment/models.py::Candidate`, `recruitment/services.py::TRANSITIONS`, `recruitment/services.py::transition`, `recruitment/views.py::kanban_board`, migration `recruitment/migrations/0031_candidate_joined_then_left.py`.
- **Agent impact**: Khi trace trạng thái ứng viên, xem `joined_then_left` là trạng thái kết thúc sau onboard; không coi đây là ứng viên đang dùng chỉ tiêu.

### 2026-10-29 — feature / npl-stock-uom-valuation

- **Change**: Chuẩn hóa hiển thị tồn NPL: `Tồn lẻ` giữ tổng số lượng theo ĐVT base, `Tồn chẵn` là số ĐVT chẵn hoàn chỉnh theo quy cách; giá trị tồn dùng tổng tồn base nhân đơn giá bình quân gia quyền của các lô còn tồn.
- **Reason**: Tránh hiểu nhầm hoặc tính trùng khi một NPL đồng thời có tồn theo ĐVT chẵn và ĐVT lẻ; đồng thời sửa định giá khi lô không có đơn giá bằng cách dùng giá cơ bản danh mục.
- **Source**: `kho_npl/services/uom.py::package_qty`, `kho_npl/services/batches.py::material_batch_totals`, `kho_npl/services/stock.py::material_stock_rows`, `kho_npl/views_material.py::material_stock_detail`, tests `kho_npl/tests_batches.py` và `kho_npl/tests_uom_rebase.py`.
- **Agent impact**: Khi trace tồn kho NPL, xem `StockBalance.quantity` là tổng ĐVT lẻ/base; không cộng thêm cột Tồn chẵn vào giá trị tồn hoặc tổng tồn.

### 2026-10-26 — feature / route-reschedule-loading

- **Change**: Giữ overlay riêng của kéo ngày công đoạn trong suốt request lưu và partial reload; chỉ dọn loading sau khi DOM lộ trình đã được cập nhật, và dọn cả khi response/lần tải lại thất bại.
- **Reason**: Ngăn bảng lộ trình hiển thị ngày cũ hoặc mất trạng thái loading trước khi backend và lần đọc lại hoàn tất.
- **Source**: `san_xuat/templates/san_xuat/plan_board.html`, hàm JavaScript `save`; endpoint `reschedule_route` trong `san_xuat/views_hub.py`; test `san_xuat/tests_plan_route_teams.py`.
- **Agent impact**: Khi trace kéo ngày, cần kiểm tra cả POST JSON và GET partial reload; backend đã dùng `reschedule_order_team_start` transaction.atomic.

### 2026-10-26 — ai-policy / bootstrap

- **Change**: Tạo `RULE.md` làm bootstrap entry point duy nhất; file này điều hướng tới policy chi tiết, code map, changelog và client-specific rules. Giữ `AI_AGENT_RULES.md` làm compatibility document.
- **Reason**: Rút gọn prompt cho mọi AI tool mà không làm mất các policy và context cần thiết.
- **Source**: `RULE.md`, `AI_AGENT_RULES.md`, `AGENTS.md`, `docs/AI_CODEBASE_MAP.md`.
- **Agent impact**: Chỉ cần yêu cầu agent đọc `RULE.md`; không cần liệt kê thủ công toàn bộ file Markdown liên quan.

### 2026-10-26 — ai-policy / approval-gate

- **Change**: Thêm approval gate: phải lên plan và hỏi người dùng trước khi code nếu dự kiến thay đổi trên 10 file hoặc liên quan đến quyết định đúng/sai, workflow, security, policy, MCP/indexing, development workflow hoặc thay đổi behavior/contract của feature.
- **Reason**: Ngăn agent tự quyết các thay đổi diện rộng hoặc nhạy cảm khi chưa thống nhất phạm vi, tiêu chí và rủi ro với người dùng.
- **Source**: `AI_AGENT_RULES.md`, mục `Mandatory approval gate`; `docs/AI_CODEBASE_MAP.md`, mục `Approval gate`.
- **Agent impact**: Được đọc context tối thiểu để lập plan, nhưng không được code, migration, đổi config diện rộng hoặc thao tác phá huỷ trước khi người dùng trả lời câu hỏi quyết định.

### 2026-10-26 — ai-policy / transparency

- **Change**: Bổ sung luật yêu cầu mọi AI agent công khai kế hoạch, lý do, phạm vi và kết quả dự kiến trước khi thực hiện các nhóm hành động; không tự ý âm thầm đọc, sửa, chạy lệnh hoặc đổi cấu hình.
- **Reason**: Người dùng cần biết agent đang chuẩn bị làm gì mà không phải phê duyệt từng bước; đồng thời tránh nhầm lẫn giữa kế hoạch minh bạch và việc yêu cầu model tiết lộ chain-of-thought nội bộ.
- **Source**: `AI_AGENT_RULES.md`, mục `Transparency before action`; `docs/AI_CODEBASE_MAP.md`, mục `Agent transparency contract`.
- **Agent impact**: Mỗi response có hành động phải bắt đầu bằng plan ngắn và thông báo trước khi đổi hướng. Có thể tự tiến hành nếu trong phạm vi yêu cầu và không có rủi ro phá huỷ, bảo mật hoặc quyết định sản phẩm quan trọng.

### 2026-10-26 — ai-policy / indexing

- **Change**: Thêm policy graph-first dùng chung tại `AI_AGENT_RULES.md`, bản đồ codebase tại `docs/AI_CODEBASE_MAP.md`, bootstrap `AGENTS.md` và cấu hình MCP local cho CodeGraph/Codebase Memory.
- **Reason**: Giảm token đọc source lặp lại và thống nhất workflow giữa các vibe-coding tool.
- **Source**: `AI_AGENT_RULES.md`, `AGENTS.md`, `docs/AI_CODEBASE_MAP.md`, `.cursor/mcp.json`.
- **Agent impact**: Đọc policy và map trước; dùng CodeGraph cho câu hỏi cấu trúc, Codebase Memory cho câu hỏi semantic/cross-boundary; chỉ mở source sau khi thu hẹp phạm vi.

### 2026-10-29 — workflow / in-production-order-tech-edit

- **Change**: Cho phép sửa snapshot BOM/OB trên chi tiết đơn hàng khi đơn còn LSX hoạt động; BOM được lưu lại, đồng bộ nhu cầu NPL KHSX mà không xóa dòng lịch sử, còn LSX chỉ nhận snapshot mới cho phần chưa hoàn thành. Thêm snapshot SMV trên `SxMoProcessStep` và audit before/after.
- **Reason**: Đáp ứng nhu cầu điều chỉnh định mức và công đoạn giữa kỳ mà không làm mất lịch sử xuất NPL hoặc trạng thái công đoạn đã hoàn thành.
- **Source**: `san_xuat/services/order_routing.py`, `san_xuat/services/plan_order_npl.py`, `san_xuat/services/dispatch.py`, `san_xuat/views_hub.py`, `san_xuat/templates/san_xuat/sales_order_detail.html`, migration `0148_sxmoprocessstep_applied_unit_smv.py`.
- **Agent impact**: Khi trace sửa kỹ thuật đơn đang chạy, bắt đầu từ `sales_order_detail` → `update_order_line_bom_overrides` / OB actions → `sync_order_npl` → `sync_active_mos_from_order`; không xóa dòng `SxOrderNplLine` cũ vì có thể đã tham chiếu phiếu xuất/đặt chỗ.

## Template cho entry mới

```markdown
### YYYY-MM-DD — type

- **Change**:
- **Reason**:
- **Source**:
- **Agent impact**:
```

Không sửa hoặc xoá entry lịch sử để phản ánh thay đổi mới. Cập nhật tài liệu hiện tại trong `docs/AI_CODEBASE_MAP.md`, sau đó thêm entry mới ở đây.
