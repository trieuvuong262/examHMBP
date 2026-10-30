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

### 2026-10-30 — workflow / bom-line-material-group

- **Change**: Dòng BOM hồ sơ (`?tab=bom&edit=1`) chọn được **[Nhóm] Nhóm gom NPL** thay cho NPL lẻ (giá trị `g:<pk>`; API `kho_npl:material_search?include_groups=1`). `BomLine.material` thành nullable + FK mới `material_group` (PROTECT), ràng buộc `sx_bom_line_material_xor_group`. Khi lên đơn, `bom_lines_snapshot` bung dòng nhóm thành mọi NPL thành viên **đang dùng**, mỗi NPL nhận đủ ĐM/hao hụt/size (snapshot cố định; đổi thành viên sau không ảnh hưởng đơn cũ). Chi tiết đơn hiện từng NPL kèm badge nhóm. KH NPL / LSX / phiếu xuất không đổi (theo mã NPL). Costing: dòng nhóm = tổng giá thành viên × ĐM. Cập nhật BOM từ đơn về hồ sơ gộp lại dòng nhóm nếu đủ thành viên + cùng ĐM. Xóa nhóm gom (vẫn xóa cứng) → `dissolve_group_bom_lines` tách dòng BOM nhóm thành NPL lẻ trước, ghi audit BOM. Lưu BOM cảnh báo NPL trùng (lẻ + trong nhóm).
- **Reason**: Không phải nhập lại từng NPL đã gộp nhóm; đơn hàng / KHSX vẫn lấy đủ mọi NPL trong nhóm.
- **Source**: `san_xuat/models.py::BomLine`, migration `san_xuat/0150_bomline_material_group`, `san_xuat/services/bom_group.py`, `bom_need.py`, `sales_orders.py`, `order_tech_publish.py`, `costing.py`, `cost_stats.py`, `bom_audit.py`, `dispatch.py`, `san_xuat/forms.py::BomLineForm`, `includes/tab_bom.html`, `kho_npl/views_material.py::_material_group_search_rows`, `kho_npl/views_settings.py::settings_deactivate`, `kho_npl/doc_prefill.py`.
- **Agent impact**: Mọi code đọc `bom.lines` phải xử lý `material_id` = NULL (dòng nhóm) — dùng `expand_bom_lines`. Snapshot đơn có thể có nhiều dòng chung `bom_line_id` (cùng dòng nhóm); `resolve_issue_material` xử lý dòng nhóm theo mã NPL.

### 2026-10-30 — module / ra-mat-sp-group-owners-m2m-fix

- **Change**: Sửa toàn bộ chỗ còn dùng FK cũ `owner`/`owner_id` của `LaunchGroupDefault` / `LaunchPlanGroupOwner` sau migration `0007_group_owners_multi` (đổi sang M2M `owners`): tạo/sửa/chi tiết kế hoạch, lịch (lọc người điều phối), việc của tôi, quyền participant; thêm `svc.owner_ids_by_group(qs)`; `settings.html` thiếu `{% load tksp_tags %}`.
- **Reason**: `FieldError: Cannot resolve keyword 'owner_id'` tại `/ke-hoach-ra-mat/ke-hoach/tao/`.
- **Source**: `ra_mat_sp/services.py`, `ra_mat_sp/views.py`, `ra_mat_sp/permissions.py`, `ra_mat_sp/templates/ra_mat_sp/settings.html`.
- **Agent impact**: Phụ trách nhóm là danh sách nhiều người — lọc bằng `owners=user`, lấy map bằng `owner_ids_by_group`, không dùng `owner`/`owner_id` trên 2 model này.

### 2026-10-30 — feature / sales-order-history-modal

- **Change**: Nút **Lịch sử cập nhật** trên topbar chi tiết ĐĐH mở modal timeline (lọc theo nhóm, tìm kiếm, mở/thu từng sự kiện) với diff chi tiết trước → sau: thông tin đơn, dòng SP (SL, size, hạn, BOM/OB), BOM trên đơn (NPL thêm/xóa/sửa ĐM, hao hụt), OB trên đơn (CĐ thêm/xóa/sửa SMV, SL/SP, bộ phận; tổng SMV/SP), xác nhận/từ chối, Cập nhật BOM/OB về hồ sơ (link mở hồ sơ), KH NPL và LSX bị đồng bộ.
- **Reason**: Truy vết ai sửa gì trên đơn đang chạy.
- **Source**: `san_xuat/services/order_history.py` (`order_history`, `log_order_event`, `ob_snapshot`, `diff_*`), `san_xuat/templates/san_xuat/includes/sales_order_history_modal.html`; ghi log mới trong `views_hub.py` (create/edit/confirm/reject + mọi action OB đơn lẻ qua `_log_ob`), `order_routing.apply_order_routing_edits(user=)` / `log_order_ob_change`, `update_order_line_bom_overrides` (`changes.kind='bom'`).
- **Agent impact**: Nhật ký đơn nằm trong `SxPlanAuditLog` (`object_type='SxSalesOrder'`, `changes.kind` ∈ order/confirm/bom/ob/publish_bom/publish_ob). Thao tác mới sửa đơn phải ghi qua `log_order_event` kèm before/after để hiện trong modal. Log cũ không có `kind` vẫn được map tương thích.

### 2026-10-30 — workflow / sales-order-publish-bom-ob-to-tech-doc

- **Change**: Chi tiết ĐĐH có 2 nút header **Cập nhật BOM** / **Cập nhật OB** (cho cả đơn, mỗi hồ sơ 1 lần). BOM: tạo `BomVersion` `vN` từ `bom_line_overrides` (ĐM/SP, hao hụt, size; giữ NVL thay thế/ghi chú/phụ phí/ProcessStep từ BOM gốc), chuyển **Đang áp dụng** (bản cũ ngừng), ghi `SxBomAuditLog new_version`; NPL không có trong danh mục bị bỏ qua và cảnh báo. OB: tạo `SxRouting` REV mới từ `SxSalesOrderRoutingLine` (SMV sản phẩm = SMV đơn hàng), **duyệt ngay** (`approve_routing`), gắn vào BOM mới nhất chưa gắn LSX và dựng lại ProcessStep. Checkbox "Trỏ đơn sang phiên bản mới": đổi `bom_version`/`routing` + remap `bom_line_id`/`source_routing_line` nhưng giữ số liệu snapshot, không tính lại NPL/LSX.
- **Reason**: Đẩy điều chỉnh kỹ thuật trên đơn ngược về hồ sơ thiết kế làm chuẩn cho đơn sau.
- **Source**: `san_xuat/services/order_tech_publish.py`, `san_xuat/views_hub.py::_handle_order_tech_publish` / `sales_order_detail` (`can_publish_order_tech`), `san_xuat/templates/san_xuat/sales_order_detail.html` (`#jpPublishTechModal`).
- **Agent impact**: Quyền = `user_can_edit_order_routing` **và** `user_can_update_module(SAN_XUAT)`; chặn khi đơn hoàn thành/hủy. Đây là luồng duy nhất ghi từ đơn → hồ sơ; các action `edit_bom_lines`/`edit_ob_lines` vẫn chỉ sửa snapshot đơn.

### 2026-10-29 — feature / sales-order-bom-edit-by-need

- **Change**: Sửa BOM trên chi tiết ĐĐH nhập theo **Nhu cầu** (quy ngược ĐM/SP = Nhu cầu ÷ SL ÷ (1 + hao hụt%)), xóa NPL dư, popup Thêm NPL chọn Nhóm → NPL từ danh mục (ảnh, mã, tên, nhóm, bộ phận, màu, quy cách, ĐVT). API `kho_npl:material_search` nhận thêm `category_id`, trả thêm `color_hex`.
- **Reason**: Kế hoạch điều chỉnh lượng NPL theo đơn thay vì định mức từng SP.
- **Source**: `san_xuat/templates/san_xuat/sales_order_detail.html`, `san_xuat/templates/san_xuat/includes/sales_order_bom_material_{modal,script}.html`, `san_xuat/views_hub.py::sales_order_detail` (`bom_overrides_json`, `bom_material_categories`), `kho_npl/views_material.py::material_search_response`.
- **Agent impact**: Lưu vẫn qua action `edit_bom_lines` → `update_order_line_bom_overrides` (snapshot `bom_line_overrides`, `qty_mode='qty'`); không sửa BOM gốc.

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

### 2026-10-29 — feature / order-detail-edit-mode

- **Change**: Giữ BOM/OB ở chế độ xem mặc định trên chi tiết đơn; nút Sửa mới mở vùng chỉnh. BOM có popup tìm/chọn NPL, thêm/xóa từng dòng và sửa nhu cầu; OB mở bộ chọn công đoạn từ thư viện, có thêm/xóa công đoạn và sửa SMV đơn hàng.
- **Reason**: Giảm thay đổi giao diện khi xem lại đơn, chỉ hiện công cụ chỉnh sửa khi người dùng chủ động bật.
- **Source**: `san_xuat/templates/san_xuat/sales_order_detail.html`, `san_xuat/templates/san_xuat/includes/sales_order_routing.html`, API `kho_npl:material_search` và `san_xuat:ie_operation_search`.
- **Agent impact**: Khi kiểm tra màn chi tiết đơn, mặc định không được coi bảng là form sửa; cần bấm Sửa BOM/OB để hiện công cụ.

## Template cho entry mới

```markdown
### YYYY-MM-DD — type

- **Change**:
- **Reason**:
- **Source**:
- **Agent impact**:
```

Không sửa hoặc xoá entry lịch sử để phản ánh thay đổi mới. Cập nhật tài liệu hiện tại trong `docs/AI_CODEBASE_MAP.md`, sau đó thêm entry mới ở đây.
