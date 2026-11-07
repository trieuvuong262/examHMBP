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

### 2026-11-07 — bugfix / đổi tổ KHSX không cập nhật LSX nên không nhập được tiến độ

- **Type**: bugfix | workflow
- **Change**: `assign_plan_team` gọi `plan_board.sync_mo_steps_team`: bước LSX đang chạy (không hủy/xong) cùng tên công đoạn (và cùng nhóm khi có mã CĐ) với bước KHSX của slug được gán tổ mới. OB đơn vẫn không bị ghi. Thêm lệnh `sync_mo_teams_from_plan` (dry-run mặc định, `--apply`, `--order-id`) đưa bước LSX đang ở tổ không phải `HRD-*` (THUÊ NGOÀI, tổ GC) về tổ KHSX; bỏ qua tên công đoạn nằm ở hai tổ trong cùng đơn.
- **Reason**: Fix `4f730c2a` bỏ `sync_active_mos_from_order` khỏi `assign_plan_team`, nên LSX giữ tổ cũ (THUÊ NGOÀI). Nhập tiến độ trên lộ trình dùng slug của tổ thực hiện (`d39`, `gc-43`) và `progress_steps_for_team` chỉ khớp work center của bước LSX → «Đơn chưa có công đoạn của tổ này».
- **Source**: `san_xuat/services/plan_board.py::assign_plan_team`, `sync_mo_steps_team`; `san_xuat/management/commands/sync_mo_teams_from_plan.py`; `san_xuat/services/order_progress_sheet.py::progress_steps_for_team`; test `san_xuat/tests_plan_placeholder_team.py`.
- **Agent impact**: Tổ thực hiện nằm ở KHSX + LSX; bộ phận nằm ở OB. Đổi tổ phải cập nhật LSX, không cập nhật OB.

### 2026-11-07 — workflow / LSX nháp cho đơn Chờ xếp

- **Type**: workflow
- **Change**: Đơn đã xác nhận đang Chờ xếp / Tạm giữ có một LSX **Nháp** cho mỗi mã hàng đủ BOM + công đoạn (`services/order_draft_mo.py::sync_order_draft_mos`). Signal `post_save` `SxSalesOrder` / `post_save`+`post_delete` `SxSalesOrderLine` xếp đồng bộ sau commit (gộp theo đơn trong một transaction): tạo mới, cập nhật SL / hạn / ngày KH / BOM / OB, hủy nháp khi bỏ dòng, mất BOM, đơn hủy hoặc bị từ chối. `release_order_to_production` dùng lại lệnh nháp (giữ mã, đồng bộ lại CĐ rồi phát hành); `ensure_order_progress_mos` đồng bộ lại CĐ trước khi mở lệnh nháp; `unrelease_order_from_production` đưa LSX về Nháp thay vì hủy. `derive_plan_status`, xếp hạng hàng đợi, tạm giữ, tải lại BOM/OB/NPL, sửa lộ trình / Kanban, `_production_status_after_reopen`, phiếu tiến độ theo đơn và GC bỏ qua LSX nháp. BOM chỉ có LSX nháp gắn đơn không bị khoá (`is_bom_locked`, `delete_bom_version`, `ie_ops`). `mo_release` chặn phát hành tay lệnh nháp của đơn Chờ xếp. Lệnh `manage.py sync_order_draft_mos [--order ID] [--apply]` (mặc định chạy thử) để tạo nháp cho đơn cũ.
- **Reason**: Đơn SXJP:005344 có trên KHSX nhưng không có LSX vì đơn xác nhận trước khi xác nhận tự Chuyển SX (03/11) và nút Chuyển SX đã tắt từ 19/10. Người dùng muốn đơn chờ xếp vẫn có LSX.
- **Source**: `san_xuat/services/order_draft_mo.py`, `san_xuat/apps.py`, `san_xuat/services/plan_board.py` (`NOT_RELEASED_MO_STATUSES`, `order_plan_step_maps`, `order_line_plan_window`, `sync_mo_steps_from_order_line`), `san_xuat/services/order_progress_sheet.py`, `san_xuat/services/dispatch.py::mo_release`, `san_xuat/management/commands/sync_order_draft_mos.py`; test `san_xuat/tests_order_draft_mo.py`.
- **Agent impact**: LSX `draft` có `sales_order` = nháp tự động, không phải lệnh đã chuyển SX; khi đếm "đơn đã có LSX" phải loại `NOT_RELEASED_MO_STATUSES` hoặc `order_draft_mo_q()`. Không tạo LSX gắn đơn ở trạng thái nháp cho mục đích khác. Nhiều đơn có `plan_status=queued` nhưng đã có LSX phát hành (mở từ nhập tiến độ) — KHSX hiển thị theo trạng thái suy ra.

### 2026-11-07 — bugfix / đơn mới bị bộ phận THUÊ NGOÀI trên lộ trình

- **Type**: bugfix | workflow
- **Change**: `SxOperationGroup.default_work_center` (migration `0160`: nhóm `SEW_*` của MAY (152A VĨNH LỘC) → THUÊ NGOÀI `NL-2026-0011`) giờ chỉ là **tổ chờ trên KHSX**. `_copy_from_routing_line` / `_copy_from_process_step` chép bộ phận OB đơn theo hồ sơ thiết kế (không lấy tổ mặc định của nhóm). `work_center_for_operation(_group)` trả lại bộ phận theo Tên bộ phận, không trả tổ mặc định. Thêm `capacity_from_hrm.placeholder_team_for_operation_group` và `plan_board.apply_placeholder_plan_teams`: khi `ensure_order_plan_steps` seed bước mới, bước thuộc nhóm có tổ chờ được ghim `board_slug`/`dept_label` theo bộ phận OB (vd. `d25` / `MAY (152A VĨNH LỘC)`) rồi gán tổ chờ. `_team_loads_from_order` lấy tổ thực hiện/năng lực của dòng bộ phận theo plan step khi tập tổ KHSX của slug khác tập tổ trên OB (trước luôn ưu tiên OB nên đơn đã giao tổ GC hiện tổ = MAY (152A VĨNH LỘC) sau khi khôi phục OB).
- **Reason**: Đơn tạo sau fix sáng 07/11 (SXJP:005378 - 1, SXJP:005377 - 2, SXJP:005377 - TE) vẫn có OB MAY = THUÊ NGOÀI và KHSX không ghim bộ phận, nên cột Bộ phận lẫn Tổ đều hiện THUÊ NGOÀI. Yêu cầu 05/11 là Bộ phận MAY, tổ THUÊ NGOÀI.
- **Source**: `san_xuat/services/order_routing.py`, `san_xuat/services/capacity_from_hrm.py`, `san_xuat/services/plan_board.py::apply_placeholder_plan_teams`, `san_xuat/services/plan_route.py::ensure_order_plan_steps`; test `san_xuat/tests_plan_placeholder_team.py`.
- **Agent impact**: Không dùng `default_work_center` làm bộ phận OB. Cột Bộ phận lộ trình lấy `dept_label` đã ghim, không có thì lấy tên tổ của day plan; muốn đổi tổ chờ thì sửa `default_work_center` của nhóm.

### 2026-11-07 — workflow / nhập sản lượng ngày trên lộ trình KHSX

- **Type**: workflow
- **Change**: Nháy đúp ô ngày công đoạn trên tab lộ trình mở modal nhập sản lượng. Bấm **Ghi nhận** chỉ cộng số vừa nhập vào **Đã làm**, xóa ô nhập và thêm một dòng lần nhập (người + SL). Tiến độ chỉ ghi khi bấm **Lưu thay đổi**. Dòng đã nhập có **Sửa**; lần sửa lưu người sửa (`SxTeamProgressLog.revised_by`). Migration `0164_team_progress_log_revision`.
- **Reason**: Nhập sai không được ghi thẳng tiến độ, và mỗi lần nhập phải cộng dồn rồi sửa được.
- **Source**: `san_xuat/templates/san_xuat/includes/plan_route_day_entry.html`, `san_xuat/views_hub.py::_route_progress_day`, `_commit_route_day_change`, `_apply_route_day_revisions`, `san_xuat/hub_models.py::SxTeamProgressLog`.
- **Agent impact**: SL trong modal là phần cộng thêm, không phải SL tuyệt đối của ngày. Bản nháp `route_day_qty` nằm trong `save_route_draft` (`entries` + `revisions`). Test: `san_xuat/tests_route_day_entry.py`.

### 2026-11-07 — workflow / bỏ khâu Giao hàng thành phẩm (gh)

- **Type**: workflow
- **Change**: Xoá khâu `gh` / nhóm `GIAO_HANG` / bước `gh_tp` / tổ chuẩn `GH` khỏi mẫu công đoạn (`progress_template`), khâu SX mặc định (`ie_models.PROCESS_STAGE_DEFAULTS`), đồng bộ thư viện (`sync_process_master`), lộ trình KHSX (`_SHEET_STAGE_*`, `_ROUTE_DEPT_ORDER`, `_LEGACY_SLUG_RANK`), map năng lực/tổ (`capacity_from_hrm`, `team_division_map`), bàn giao (`handover_status`), resolver nhóm khi import (`operation_group_resolve`), màu khâu, tiêu chí QC mặc định, menu «Tổ giao hàng» (`team_work_gh`) và choices `team_slug`. Luồng còn 5 tổ: Cắt → In - Ép → Thêu → May → Ủi - Gấp xếp; cột cuối lộ trình vẫn là Nhập kho (`kho`). **YCNTP** giờ lấy SL đã xong từ bước **Gấp xếp** (`dispatch.FG_SOURCE_STEP_KEY = "ht_gap"`) cho prefill, chặn vượt SL và trạng thái partial/done. Nhóm `FOD_`/`PACK` fallback về `ht` (trước là `gh`); lệnh `sync_operation_group_departments` map `FOD_` → «Gấp xếp». Migration `0162` (chỉ choices) + `0163_retire_gh_stage_data` tắt tiêu chí QC `gh`, nhóm `QC-GH`, khâu/nhóm/tổ `GH`, map `gh`, xoá màu `gh` (reverse bật lại).
- **Reason**: Người dùng bỏ khâu Giao hàng thành phẩm. Production chưa từng có tiến độ `gh_tp`, tổ `GH`, nhóm `GH` hay YCNTP; mô phỏng 27.560 dòng routing/plan step cho thấy không dòng nào đổi bộ phận.
- **Source**: `san_xuat/services/progress_template.py`, `san_xuat/services/dispatch.py::_completed_progress_lines`, `san_xuat/services/plan_board.py`, `san_xuat/services/capacity_from_hrm.py`, `hrm/submenu_registry.py`, `san_xuat/migrations/0162_*`, `0163_*`.
- **Agent impact**: Không còn slug `gh`; «Giao hàng may» (`may_giao`) là bước khác của tổ May. Muốn đổi mốc nhập thành phẩm thì sửa `FG_SOURCE_STEP_KEY`. Ảnh PNG/PDF training trong `san_xuat/docs/` cần render lại từ `render_training_diagrams.py` / `build_workflow_pdf.py`.

### 2026-11-07 — workflow / bỏ bộ phận QA khỏi sản xuất

- **Type**: workflow
- **Change**: Bộ phận HR tên `QA` (phòng ĐẢM BẢO CHẤT LƯỢNG) vẫn giữ trên Nhân sự nhưng bị loại khỏi sản xuất qua `SX_EXCLUDED_DIVISION_NAMES` / `sx_excluded_division_q()`: không còn trong `hr_divisions_for_ie_groups` (menu Tiến độ tổ, thiết lập tổ, dropdown Tên bộ phận nhóm công đoạn + bộ phận NPL, thứ tự lộ trình), không được `sync_capacity_from_hrm` tạo/bật `HRD-*`, không có trong dropdown bộ phận của form Năng lực. Bỏ bậc `('qa',)` khỏi `_ROUTE_DEPT_ORDER` và khóa `qa` khỏi `_IE_WC_TO_HR_KEYS`; bộ phận không khớp khâu vẫn xếp hạng `kho` (10) như trước nên Giao hàng thành phẩm (`gh`) không đổi vị trí. Migration `0161_hide_qa_division_from_production` tắt `SxWorkCenter` `HRD-{QA}` và dòng `SxTeamDivisionMap` của QA (reverse bật lại).
- **Reason**: QA không tham gia quy trình sản xuất (0 nhân sự, không có kế hoạch/tiến độ/QC gắn vào); người dùng yêu cầu bỏ khỏi mọi màn hình và logic sản xuất mà không đổi luồng.
- **Source**: `san_xuat/services/capacity_from_hrm.py`, `san_xuat/services/plan_board.py::_factory_slug_rank`, `san_xuat/forms_phase3.py::WorkCenterForm`, `san_xuat/migrations/0161_hide_qa_division_from_production.py`.
- **Agent impact**: Muốn loại thêm bộ phận HR khỏi sản xuất thì thêm tên vào `SX_EXCLUDED_DIVISION_NAMES`, đừng tắt bộ phận trên Nhân sự. Vai trò «QA/QC» trong `thiet_ke_sp` là luồng duyệt thiết kế khác, không liên quan.

### 2026-11-07 — bugfix / đơn gia công chỉ hiện một tổ

- **Type**: bugfix | workflow
- **Change**: Lưới Công việc tổ và danh sách phân công chỉ giữ đơn ở tổ gia công của work center cuối trong `SxSalesOrderPlanStep`. Lịch ngày còn sót ở tổ GC khác bị bỏ khi tổ đích đã có lịch riêng; nếu tổ đích chưa có lịch thì sản lượng lịch cũ được tính trên bảng tổ đích. Lịch ngày GC không còn work center nào trên lộ trình thì bỏ khỏi bảng GC (đơn ở lại tổ nội bộ của lộ trình, ví dụ `d25` chứ không kèm `gc-47`). Không ghi đè `SxOrderTeamDayPlan`.
- **Reason**: Đơn đã chuyển khỏi THUÊ NGOÀI (`gc-47`) vẫn hiện ở đó vì lưới đọc lịch ngày cũ, trong khi snapshot lộ trình đã trỏ tổ khác.
- **Source**: `san_xuat/services/team_output_report.py::_sole_gc_team`, `_team_plan_hits`, `_plan_by_team_day`; `san_xuat/services/team_work.py::apply_own_plan_team`; test `san_xuat/tests_gc_board_owner.py`.
- **Agent impact**: Đối chiếu work center GC cuối trên snapshot, không xóa lịch ngày để sửa hiển thị. Bộ phận nội bộ (cắt, may, …) vẫn hiện đơn của công đoạn đó.

### 2026-11-07 — bugfix / SL đã làm khi ô bộ phận giao cho tổ thuộc bộ phận HR khác

- **Type**: bugfix | workflow
- **Change**: `handover_status.done_qty_by_order_team_day` cộng SL của tổ nhập tiến độ (`d{id}` theo nhãn tổ) vào ô day plan được giao cho work center `HRD-{id}` của chính tổ đó, khi tổ không có ô riêng trên đơn (vd. ô MAY `d25` giao cho MAY (19 CHIẾN LƯỢC) `HRD-39`, SL nhập dưới `d39`).
- **Reason**: Dòng Tổng MAY trên lộ trình hiện 0 dù tổ đã nhập đủ, nên nút «Hoàn thành» (mọi dòng Tổng > 80%) không hiện (đơn SXJP:005318 - 6).
- **Source**: `san_xuat/services/handover_status.py::done_qty_by_order_team_day`; dùng bởi `plan_board._done_qty_by_order_team(_day)`, `route_stage_rows_can_complete`, Tiến độ hàng hoá.
- **Agent impact**: Mô phỏng trên production trước khi đổi: 177 đơn đang chạy, chỉ đơn 198 đổi khóa `d39 → d25`. Sau deploy phải `refresh_route_sheets` cho đơn bị ảnh hưởng vì `can_complete` nằm trong cache `SxRouteSheet.payload`.

### 2026-11-07 — workflow / hồ sơ thiết kế là nguồn bộ phận của OB

- **Type**: workflow | bugfix
- **Change**: `plan_board.assign_plan_team` không còn ghi `work_center` vào OB snapshot của đơn hàng và không gọi `sync_active_mos_from_order` khi đổi tổ trên KHSX. Kế hoạch chỉ thay đổi phân công tổ thực hiện trên `SxSalesOrderPlanStep`; bộ phận theo mã công đoạn tiếp tục lấy từ hồ sơ thiết kế/OB chuẩn.
- **Reason**: Không để thay đổi tổ trong kế hoạch sản xuất ghi ngược làm đổi bộ phận OB của đơn hàng từ MAY sang Thuê Ngoài.
- **Source**: `san_xuat/services/plan_board.py::assign_plan_team`; `san_xuat/services/order_routing.py`; `docs/AI_CODEBASE_MAP.md`.
- **Agent impact**: Khi đổi tổ, kiểm tra `SxSalesOrderPlanStep` và LSX snapshot riêng; không dùng thao tác phân công tổ để sửa `SxSalesOrderRoutingLine`.

### 2026-11-07 — maintenance / khôi phục bộ phận OB đơn hàng bị tổ KHSX ghi đè

- **Type**: workflow | bugfix
- **Change**: Thêm `restore_order_ob_departments` (dry-run mặc định, `--apply`, `--order-id`, `--order-code`, `--include-unmatched`). Đưa `work_center/work_center_code` của `SxSalesOrderRoutingLine` về dòng routing nguồn chỉ khi: slug bộ phận của dòng OB trùng slug của routing nguồn, routing nguồn trỏ vào bộ phận `HRD-*`, và cặp (slug, tổ hiện tại) có trong `SxSalesOrderPlanStep`/`SxOrderTeamDayPlan` của đơn. Không đụng plan step, day plan, LSX.
- **Reason**: `assign_plan_team` cũ đã ghi tổ KHSX (THUÊ NGOÀI, tổ GC…) vào OB của hàng trăm đơn, làm công đoạn MAY hiển thị sai bộ phận (ví dụ đơn 275).
- **Source**: `san_xuat/management/commands/restore_order_ob_departments.py`.
- **Agent impact**: Dòng lệch khác (routing master sửa sau khi chụp snapshot, OB sửa tay, master bị publish từ OB lỗi) chỉ được liệt kê `SKIP`; xem từng đơn trước khi dùng `--include-unmatched`. Sau khi khôi phục, sửa OB trên đơn sẽ gọi `sync_order_plan_steps_from_ob` dựng lại KHSX theo OB và bỏ phân công tổ thủ công.


### 2026-11-07 — ai-policy / production and local URL safety

- **Type**: ai-policy
- **Change**: Added an environment check rule: URLs beginning with `https://portal.justplay.vn/` require checking the VPS/production state first; URLs beginning with `http://127.0.0.1:8000/` are treated as local and may be updated within scope; other URLs require clarification.
- **Reason**: Prevent accidental production changes while keeping local development workflow flexible.
- **Source**: `RULE.md`, `AI_AGENT_RULES.md`, `docs/AI_CODEBASE_MAP.md`.
- **Agent impact**: Determine the target environment from the URL before checking or modifying the application.

### 2026-11-06 — feature / superuser code management explorer

- **Type**: feature | architecture
- **Change**: Thêm submenu `Quản lý code` trong `Quản Trị Hệ thống`, chỉ superuser truy cập được. Trang hiển thị app, URL, function/file-line, model/table, quan hệ field và Mermaid diagram từ metadata Django + AST.
- **Reason**: Cho phép quản trị viên tra cứu dependency trước khi thêm hoặc sửa chức năng mà không lộ nội dung source, secret hay dữ liệu nghiệp vụ.
- **Source**: `audit/architecture_service.py`, `audit/views_architecture.py`, `audit/urls.py`, `templates/audit/architecture_map.html`, `templates/includes/portal_sidebar.html`, `audit/tests_architecture.py`.
- **Agent impact**: Route `/nhat-ky/quan-ly-code/` dùng decorator + `PermissionDenied`; 403 cho authenticated non-superuser. Data là static metadata, cần CodeGraph/runtime trace để xác minh sâu hơn.

### 2026-11-06 — ai-policy / add-change feature checklist


### 2026-11-06 — bugfix / lưu lộ trình trả lỗi JSON cho AJAX

- **Type**: bugfix
- **Change**: Bổ sung `save_route_draft` vào các nhánh response lỗi AJAX của `plan_board`; lỗi nghiệp vụ, lỗi bất ngờ hoặc thiếu quyền giờ trả JSON `{ok: false, error: ...}` thay vì redirect về HTML.
- **Reason**: Frontend lưu lộ trình gọi `res.json()`, nên response HTML bắt đầu bằng `<!DOCTYPE` gây lỗi `Unexpected token '<'` và che mất thông báo thật.
- **Source**: `san_xuat/views_hub.py::plan_board`; regression test `san_xuat/tests_plan_route_teams.py::RescheduleRouteViewTests.test_post_json_save_route_draft_error_is_json`; template `san_xuat/templates/san_xuat/includes/plan_route_edit_state.html`.
- **Agent impact**: Khi thêm action AJAX mới vào `plan_board`, phải đưa action vào toàn bộ nhánh JSON lỗi tương ứng với nhánh thành công.

### 2026-11-06 — ai-policy / add-change feature checklist


- **Type**: ai-policy | architecture
- **Change**: Bổ sung quy trình bắt buộc khi thêm/sửa chức năng: trace URL → view → service → model/table, chạy architecture map và CodeGraph, kiểm tra permission/migration/test, cập nhật code map/changelog và báo giới hạn phân tích tĩnh.
- **Reason**: Giảm bỏ sót dependency, bảng dữ liệu, migration, quyền và tài liệu khi thay đổi chức năng hiện hữu.
- **Source**: `RULE.md`, `AI_AGENT_RULES.md`, `docs/AI_CODEBASE_MAP.md`, `docs/architecture/README.md`.
- **Agent impact**: Luôn trace trước khi sửa; nếu ảnh hưởng workflow, security, data, permission, policy hoặc trên 10 file thì phải dừng ở approval gate.

### 2026-11-06 — bugfix / một đơn chỉ hiển thị ở tổ gia công đích

- **Type**: bugfix | workflow
- **Change**: `apply_own_plan_team` ưu tiên work center gia công hiện hành trong snapshot lộ trình khi lọc bảng Công việc tổ; dữ liệu lịch cũ còn sót ở tổ GC khác không làm cùng đơn xuất hiện đồng thời ở hai bảng. Board nội bộ/THUÊ NGOÀI cũng loại đơn đã có work center GC hiện hành trong snapshot, thay vì chỉ dựa vào day-plan.
- **Reason**: Đơn đã chuyển về tổ `50-Phú TV` (`gc-37`) nhưng vẫn xuất hiện ở `THUÊ NGOÀI` (`gc-47`).
- **Source**: `san_xuat/services/team_work.py::apply_own_plan_team`; regression test `san_xuat/tests_plan_route_teams.py::TeamWorkGcOwnershipTests`.
- **Agent impact**: Khi kiểm tra đơn gia công bị trùng bảng, đối chiếu `SxSalesOrderPlanStep.work_center` theo thứ tự snapshot; không xóa dữ liệu tiến độ hoặc phiếu GC chỉ để sửa hiển thị.

### 2026-11-06 — maintenance / command sửa bộ phận route board cho tổ thuê ngoài

- **Type**: workflow
- **Change**: Thêm `repair_route_subcontract_departments` với dry-run mặc định và `--apply`, chỉ cập nhật `SxSalesOrderPlanStep.board_slug/dept_label` khi mapping từ routing line là duy nhất; sau khi apply rebuild route sheet bị ảnh hưởng.
- **Reason**: Cho phép sửa dữ liệu production có kiểm soát mà không động vào routing master/OB dùng chung.
- **Source**: `san_xuat/management/commands/repair_route_subcontract_departments.py`.
- **Agent impact**: Luôn chạy dry-run trước; không dùng `align_route_departments` cho việc sửa snapshot thuê ngoài nếu chưa muốn thay đổi routing master.

### 2026-11-06 — bugfix / tổ thuê ngoài không thay thế bộ phận OB trên route board

- **Type**: bugfix | workflow
- **Change**: `_step_team_slug()` giữ slug bộ phận từ nhóm công đoạn OB khi work center được gắn là tổ thuê ngoài; work center thuê ngoài vẫn được giữ làm tổ thực hiện và dùng cho nhập tiến độ.
- **Reason**: Route board hiển thị mã/tên tổ thuê ngoài như `40-Rong HCM` ở cột Bộ phận thay vì bộ phận OB như `MAY`.
- **Source**: `san_xuat/services/inter_step_times.py::_step_team_slug`.
- **Agent impact**: Không suy ra slug bộ phận từ work center thuê ngoài; phân biệt bộ phận OB với tổ năng lực/slug `gc-*` của bảng Công việc tổ.

### 2026-11-06 — bugfix / SL đơn hàng trên route board

- **Type**: bugfix
- **Change**: Truyền `PlanBoardRow.total_qty` vào `PlanTimelineRow`, serialize/deserialize trong `SxRouteSheet.payload`, và template có fallback về `order.total_qty` cho cache cũ.
- **Reason**: Route board đã có tổng SL đơn ở row nguồn nhưng payload cache bỏ qua trường này, khiến cột «SL đơn hàng» hiển thị trống.
- **Source**: `san_xuat/services/plan_board.py::PlanTimelineRow/build_order_timeline`, `san_xuat/services/route_sheet.py::_dump_timeline/_hydrate_row`, `san_xuat/templates/san_xuat/includes/plan_board_route_product.html`.
- **Agent impact**: Khi thêm trường hiển thị vào route board, phải kiểm tra đủ chuỗi DTO → serializer → cache loader → template và test cả cache cũ.

### 2026-11-06 — workflow / Công việc tổ khớp bộ phận và tổ

- **Type**: workflow | feature
- **Change**: Board submenu HR chỉ nhận công đoạn khớp đồng thời work center của bộ phận và tổ nội bộ; công đoạn chuyển sang tổ gia công `gc-<work_center_id>` không xuất hiện ở board `d{id}`. Phân công và mở phiếu tiến độ trực tiếp cũng áp dụng cùng điều kiện.
- **Reason**: Một bộ phận có nhiều tổ; MAY giao THUÊ NGOÀI phải đi qua menu Gia công, không lẫn vào submenu MAY nội bộ.
- **Source**: `san_xuat/services/order_progress_sheet.py::progress_steps_for_team`, `san_xuat/services/team_work.py::build_team_work_rows/assign_team_work`, `san_xuat/views_hub.py::team_work_progress`, `san_xuat/services/team_division_map.py`.
- **Agent impact**: Không fallback từ `group_key` sang board bộ phận khi work center thực tế là tổ gia công; kiểm tra `work_center_id/code` trước khi hiển thị hoặc phân công.

### 2026-11-05 — bugfix / chuyển tổ gia công phải vào đúng Công việc tổ

- **Type**: workflow | feature
- **Change**: `assign_plan_team` đồng bộ snapshot LSX đang hoạt động và đổi day plan sang slug `gc-<work_center_id>` khi work center đích là tổ gia công; slug bộ phận KHSX vẫn giữ nguyên để tính lịch.
- **Reason**: Trước đây chỉ đổi work center, trong khi `SxOrderTeamDayPlan` vẫn mang slug `d25`, khiến route board hiển thị đúng tổ nhưng bảng `/cong-viec-to/gc-44/` không thấy đơn.
- **Source**: `san_xuat/services/plan_board.py::assign_plan_team`, `san_xuat/services/order_routing.py::sync_active_mos_from_order`, `san_xuat/services/team_division_map.py::gc_work_center_items`.
- **Agent impact**: Khi đổi sang tổ gia công, phải cập nhật cả work center, snapshot LSX và slug day plan; không chỉ cập nhật `SxSalesOrderPlanStep`.

### 2026-11-05 — bugfix / đổi tổ trên bảng lộ trình cập nhật ngay

- **Type**: workflow | feature
- **Change**: Sau thao tác `assign_plan_team` trên bảng KHSX, route sheet của đơn vừa đổi tổ được dựng lại đồng bộ trước khi trả phản hồi AJAX.
- **Reason**: Tránh lần reload ngay sau khi chọn work center mới đọc snapshot `SxRouteSheet` cũ trong lúc worker chưa rebuild xong.
- **Source**: `san_xuat/views_hub.py::plan_board`, `san_xuat/services/plan_board.py::assign_plan_team`, `san_xuat/services/route_sheet.py::refresh_route_sheets`.
- **Agent impact**: Khi đổi tổ trên route board, kiểm tra cả dữ liệu nguồn và payload `SxRouteSheet`; không kết luận thao tác thất bại chỉ từ snapshot cũ.

### 2026-11-05 — feature / submenu Công việc tổ cho tổ gia công

- **Type**: feature | workflow
- **Change**: Submenu Công việc tổ bổ sung nhóm Gia công, lấy động từ `GcPartner` đang hoạt động và đã gắn `SxWorkCenter` active. Mỗi tổ dùng slug riêng `gc-<work_center_id>` và lọc công đoạn theo đúng work center, không theo bộ phận HR/division.
- **Reason**: Tách các tổ như THUÊ NGOÀI, 31-Sòn TV, 34-Triệu TV khỏi submenu bộ phận HR như MAY, đồng thời vẫn cho planner chọn work center thủ công trong Năng lực sản xuất.
- **Source**: `san_xuat/services/team_division_map.py::gc_work_center_items`, `gc_team_from_slug`; `san_xuat/services/progress_template.py::team_by_slug`; `san_xuat/services/order_progress_sheet.py::progress_steps_for_team`; `templates/includes/portal_sidebar.html`.
- **Agent impact**: Không dùng `division_id` hoặc slug `d{id}` để lọc tổ gia công; chỉ đối tác active có work center active mới xuất hiện.


### 2026-11-04 — feature / xem trước OB trên form đơn hàng khớp với OB được lưu

- **Type**: feature
- **Change**: `sales_order_line_versions_api` không còn lấy công đoạn từ OB mặc định khác hoặc từ BOM khi OB đang chọn không có công đoạn. API chỉ xem trước OB đang chọn (phải thuộc mã hàng, nếu không thì coi như chưa chọn), không chọn thì dùng OB mặc định. OB đó rỗng thì trả `steps=[]`, `routing_empty=true`, `routing_label`, và form đơn hàng hiện cảnh báo «OB đang chọn chưa có công đoạn». Chỉ khi mã hàng không có OB nào thì mới xem trước công đoạn từ BOM (`steps_source='bom'`). Khung OB trên form giờ hiện các công đoạn BOM này khi dòng không chọn OB nhưng có chọn BOM (trước đây bị ẩn dù khi lưu vẫn chép vào đơn). Khi chép từ BOM, `_copy_from_process_step` lấy mã/tên công đoạn qua `_step_code_and_name` (mã trống thì lấy mã của công đoạn thư viện), và `seed_order_line_routing` đánh SEQ từ số gốc của bước BOM, giống hệt `process_preview_from_bom`, nên SMV sửa trên form khớp được vào đúng dòng.
- **Reason**: Đơn 216: form sửa hiện 32 dòng OB mượn từ nguồn khác, nhưng khi lưu `seed_order_line_routing` chỉ chép từ OB đã chọn (rỗng), nên đơn lưu xong vẫn không có OB. Ngược lại, với mã hàng chỉ có BOM, form ẩn công đoạn nhưng khi lưu vẫn chép vào đơn.
- **Source**: `san_xuat/views.py::sales_order_line_versions_api`, `san_xuat/templates/san_xuat/sales_order_form.html::renderBoards`, `san_xuat/services/order_routing.py::seed_order_line_routing`, `_copy_from_process_step`.
- **Agent impact**: Preview OB trên form phải giữ đúng thứ tự nguồn của `seed_order_line_routing`: có OB thì chỉ dùng OB đó, không có OB thì mới dùng BOM. Không thêm cơ chế dự phòng chỉ ở một phía.

### 2026-11-04 — feature / vananh, thoptt xem toàn bộ tab «Bộ phận» ở /kpi/

- **Type**: feature
- **Change**: Username trong `kpi/views.py::_KPI_DIVISION_TAB_ALL_VIEWERS` (`vananh`, `thoptt`, so khớp không phân biệt hoa thường) thấy tab «Bộ phận» ở `kpi_list_view` với KPI của mọi nhân sự đang làm việc (trừ chính họ), và bộ lọc có mọi bộ phận đang hoạt động. Chỉ áp dụng cho danh sách: nút «Mở» chỉ hiện với bảng mà họ vốn đã mở được chi tiết (`_kpi_detail_openable_ids`, khớp `_kpi_detail_roles`). Quyền sửa/xoá/giao KPI vẫn theo phạm vi cũ. `kpi_detail_view`, tổng kết KPI (`_kpi_division_choices` mặc định) và các màn hình khác không đổi.
- **Reason**: HCNS cần xem toàn bộ KPI bộ phận trên một màn hình, nhưng không mở rộng quyền ở chỗ khác.
- **Source**: `kpi/views.py::_is_kpi_division_tab_all_viewer`, `_kpi_detail_openable_ids`, `_kpi_division_choices(all_divisions=)`, `kpi_list_view`; `kpi/templates/kpi/kpi_list.html` (`dk.can_open_detail`).
- **Agent impact**: Thêm/bớt người xem thì sửa `_KPI_DIVISION_TAB_ALL_VIEWERS`. Đừng thêm họ vào `is_global_report_viewer`, vì hàm đó mở quyền toàn công ty ở nhiều module.

### 2026-11-04 — workflow / KPI tháng của TBP/TP bỏ bước quản lý chấm

- **Type**: workflow
- **Change**: Bảng KPI tháng của người có vai trò Trưởng bộ phận hoặc Trưởng phòng (tính cả kiêm nhiệm, `effective_roles`) không còn bước «Chờ quản lý chấm». Khi nộp tự đánh giá, bảng chuyển thẳng `draft` → `mgr_reviewed` («Chờ giám đốc phê duyệt»). Ở bước này chỉ giám đốc chấm cột Quản lý (theo `MonthlyKpi.can_manager_edit`) rồi «Phê duyệt & khoá». «Trả lại» từ `mgr_reviewed` về thẳng `draft`. Bảng TBP/TP đang ở `self_submitted` tự chuyển sang `mgr_reviewed` khi mở danh sách KPI, mở chi tiết hoặc thao tác quy trình. Luồng cho các vai trò khác giữ nguyên.
- **Reason**: TBP/TP trực thuộc giám đốc, nên giám đốc chấm cuối là đủ.
- **Source**: `kpi/views.py::_skips_manager_step`, `_promote_director_only_board(s)`, `kpi_list_view`, `kpi_detail_view`, `kpi_workflow_action`. Khối «Quy tắc / Quy trình» trên `kpi/templates/kpi/kpi_detail.html` đã bị bỏ theo yêu cầu.
- **Agent impact**: Muốn đổi những vai trò được bỏ bước QL thì sửa `_DIRECTOR_ONLY_KPI_ROLES` trong `kpi/views.py`. Không có migration, trạng thái vẫn dùng 4 giá trị cũ.

### 2026-11-04 — feature / tài khoản demo chỉ xem

- **Type**: feature | workflow
- **Change**: Thêm `ReadOnlyAccountMiddleware` (sau `DepartmentModuleAccessMiddleware`) áp dụng cho username trong `hrm/user_search.py::READ_ONLY_USERNAMES` (`demo`). Tài khoản này không được thêm/sửa/xóa/in/xuất/tải về/đổi hoặc đặt lại mật khẩu, không vào được DS nhân sự, và bị ẩn khỏi DS nhân sự, file export, sơ đồ tổ chức và ô chọn người (`HIDDEN_HRM_LIST_USERNAMES`). Không bị ép chấm công. Không bao giờ được chọn làm người duyệt (`find_manager_with_subordinate`) và không làm phòng có thêm bước duyệt Trưởng phòng (`department_has_department_heads_extended`). Không tạo/đồng bộ tài khoản Odoo (SSO) hay NAS LDAP. Xem báo cáo/KPI toàn công ty như TGĐ (`hrm/permissions.py::is_global_report_viewer` trả True) nhưng mở báo cáo không đánh dấu «đã xem» (`reports/report_lock.py::lock_report_on_supervisor_view`). Được mở thêm module Thiết kế SP và Kế hoạch ra mắt ngoài cấu hình phòng ban (`hrm/module_permissions.py::READ_ONLY_EXTRA_MODULES`). `_PROTECTED_USERNAMES` vẫn chỉ gồm `admin`.
- **Reason**: Cần tài khoản demo cho khách xem portal với phạm vi quyền Trưởng phòng IT nhưng không thể thay đổi dữ liệu.
- **Source**: `PortalJustPlay/middleware.py::ReadOnlyAccountMiddleware`; `PortalJustPlay/settings.py::MIDDLEWARE`; `hrm/user_search.py::is_read_only_account`; `zalo/password_reset.py::resolve_user_for_password_reset`; `zalo/email_password_reset.py::_user_can_reset`; `cham_cong/services.py::_should_force_punch`; test `hrm/tests_read_only_account.py`.
- **Agent impact**: Thêm tài khoản chỉ xem mới = thêm username vào `READ_ONLY_USERNAMES`. Middleware chặn GET theo token của `url_name`; URL thao tác mới nên đặt tên chứa động từ (`*_delete`, `*_export`, `*_print`, `*_edit`…) để được chặn tự động. Nhóm quyền của demo là `PermissionGroup` riêng; lệnh `grant_export_print` bật export/print cho mọi nhóm nhưng middleware vẫn chặn.

### 2026-11-04 — workflow / tổ gia công xác nhận đã nhận NPL trên cổng pn

- **Type**: workflow | feature
- **Change**: Trang chi tiết phiếu trên cổng đối tác (`order_detail`) có mục «NPL nhận từ JustPlay» (ảnh, SL xuất, SL thực nhận, ghi chú). Sau khi bấm «Nhận đơn», đối tác nhập SL thực nhận từng dòng NPL `direction='out'`; khác SL xuất thì bắt buộc ghi chú. Sửa lại được xác nhận cho đến khi có báo sản lượng đầu tiên. Không chặn báo sản lượng và không tạo/sửa chứng từ kho. Trang chi tiết phiếu nội bộ hiện thẻ «Đối tác xác nhận NPL» (đủ / lệch / chưa xác nhận). Thu hồi, từ chối đơn hoặc sửa dòng NPL phía nội bộ sẽ xóa xác nhận cũ.
- **Reason**: Cần bằng chứng tổ gia công đã nhận đúng NPL JustPlay xuất đi, và thấy sớm chênh lệch.
- **Source**: `san_xuat/hub_models.py::SxSubcontractMaterialLine` (`qty_confirmed`, `confirm_note`, `confirmed_at`, `confirmed_by`, `is_mismatch`); `san_xuat/services/gc_output.py::confirm_materials`, `clear_material_confirmations`, `material_image_urls`; `san_xuat/partner_portal/views.py::_handle_order_post`, `order_detail`; `GcPartnerActivity.ACTION_CONFIRM_MATERIALS`; templates `partner_portal/order_detail.html`, `san_xuat/subcontract_detail.html`, `san_xuat/includes/gc_material_thumb.html`; migration `0159`.
- **Agent impact**: Xác nhận NPL chỉ là đối soát, không đụng `stock_issue`. Dòng NPL phía nội bộ bị xóa và tạo lại khi sửa phiếu (`update_subcontract_order`), nên xác nhận đối tác mất theo. Trong template, không dùng `x.account.username` làm tham số `default` khi FK có thể null (gây `VariableDoesNotExist`).

### 2026-11-04 — workflow / đơn giản hóa bảng giá và tài khoản đối tác gia công

- **Type**: workflow
- **Change**: `GcPriceRule` chỉ còn giá chung theo đối tác × công đoạn (bỏ `product_code`, `product_name`) và có hiệu lực ngay khi thêm (bỏ `status`, `approved_by`, `approved_at`, hàm `approve_price_rule`, quyền duyệt giá). `GcPartnerAccount` bỏ `role`: mọi tài khoản đối tác đều toàn quyền (nhận/từ chối đơn, xem giá, KPI, báo sản lượng); `auth.is_owner` chỉ còn kiểm tra đã đăng nhập. Danh sách duyệt sản lượng bỏ bộ lọc và gộp cột Phiếu/đối tác/người báo. Trang thống kê gia công bỏ 4 thẻ tổng.
- **Reason**: Yêu cầu nghiệp vụ: giá áp chung cho mọi sản phẩm, không duyệt giá, chỉ chủ xưởng gia công thao tác.
- **Source**: `san_xuat/partner_models.py`; `san_xuat/services/gc_partner.py::resolve_gc_price`, `validate_price_rule`; `san_xuat/partner_portal/auth.py`; `san_xuat/views_gc_partner.py`; `san_xuat/list_grid.py` (`gc_partner`, `gc_account`, `gc_output`); migrations `0156`–`0158`.
- **Agent impact**: `resolve_gc_price(partner_id, team_slug, on_date)` không còn nhận `product_code`. `validate_price_rule` được gọi lúc thêm giá để chặn trùng hiệu lực. Duyệt sản lượng (`GcOutputReport`) là luồng riêng và vẫn giữ nguyên.

### 2026-11-03 — infra / gỡ site portfolio.phongkstudio.com

- **Type**: infra
- **Change**: Xoá `PortalJustPlay/nginx/portfolio.conf`, `portfolio-ssl.conf` và hai mount tương ứng trong `docker-compose.yml` / `docker-compose.ssl.yml`. Trên VPS đã xoá container + image `portfolio`, thư mục `/opt/portfolio` và chứng chỉ Let's Encrypt của domain.
- **Reason**: Ngừng chạy web portfolio trên VPS.
- **Source**: `docker-compose.yml` (service `nginx`), `docker-compose.ssl.yml`.
- **Agent impact**: Nginx portal không còn vhost nào ngoài portal/erp/pn/ip. Network `justplay_edge` vẫn giữ vì `nginx` khai báo nó là external.

### 2026-11-03 — feature / chip SX và danh sách LSX trên chi tiết đơn

- **Type**: feature (UI) | bugfix
- **Change**: `production_status_summary` chỉ trả `chua_du_lenh` khi còn mã SP (dòng SL > 0) chưa có LSX còn hiệu lực (`order_codes_missing_mo`). Đủ LSX nhưng chưa bắt đầu (draft/released) → trạng thái mới `da_co_lenh` «Đã có lệnh». Header chi tiết đơn liệt kê mã LSX (không tính đã hủy) kèm link `dispatch_mo_detail`.
- **Reason**: Đơn đã có đủ LSX phát hành vẫn hiện «Chưa lập đủ lệnh», người dùng hiểu là đơn chưa có lệnh sản xuất.
- **Source**: `san_xuat/services/sales_orders.py::production_status_summary`, `order_codes_missing_mo`, `PROD_STATUS_LABELS`; `san_xuat/views_hub.py::sales_order_detail` (context `order_mos`); `san_xuat/templates/san_xuat/sales_order_detail.html`; `san_xuat/tests/test_order_routing.py`.
- **Agent impact**: `production_status_summary(order, mos)` nhận sẵn danh sách LSX để tránh query `related_mos` hai lần. Thêm trạng thái chip mới phải bổ sung cả nhãn trong `PROD_STATUS_LABELS` và CSS `.is-prod-<key>` trong template chi tiết đơn.

### 2026-11-03 — workflow / xác nhận đơn tự tạo LSX

- **Type**: workflow
- **Change**: `confirm_sales_order` sau khi tạo KHSX và lịch tổ sẽ tự tạo, gắn đơn và phát hành LSX cho mọi mã sản phẩm có số lượng dương trong cùng transaction. Xác nhận rollback nếu thiếu BOM/công đoạn, tạo LSX lỗi hoặc không tạo đủ LSX.
- **Reason**: Đơn đã xác nhận phải luôn có cả KHSX và LSX, tránh trạng thái chỉ có kế hoạch nhưng không có lệnh để theo dõi sản xuất.
- **Source**: `san_xuat/services/sales_orders.py::confirm_sales_order`, `san_xuat/services/plan_board.py::release_order_to_production`, `san_xuat/tests/test_order_routing.py`.
- **Agent impact**: Không còn giả định xác nhận chỉ đưa đơn vào hàng đợi. Trước khi xác nhận, mọi dòng dương phải có BOM và ít nhất một nguồn công đoạn từ snapshot đơn, OB hoặc BOM; thành công trả về đơn ở trạng thái kế hoạch `released` với LSX đã phát hành.

### 2026-11-02 — workflow / gộp "Tổ gia công" và "Đối tác" thành một (GcPartner)

- **Type**: workflow | feature | schema
- **Change**: Menu Gia Công bỏ khái niệm kép. "Tổ gia công" giờ = `GcPartner` (đơn vị thuê ngoài, song song tổ nội bộ qua `team_slug`, có tài khoản cổng pn, giá, KPI, duyệt sản lượng).
  - `GcPartnerForm` bỏ FK `work_center`; thêm nhãn tổ (Mã tổ, Tên tổ, Công đoạn = team_slugs, Năng lực/ngày) + giữ trường doanh nghiệp (MST, liên hệ, thanh toán). `team_slugs` set initial từ instance, lưu qua `cleaned_data`.
  - `views_gc.gc_team_list` render lại `gc_partner_list`; `gc_team_create` → `?add=1`; `gc_team_edit(pk)` → `gc_partner_detail`. Sidebar gộp còn: Tổ gia công, Thuê gia công, Tài khoản, Thống kê, KPI, Duyệt sản lượng (bỏ mục "Đối tác" riêng). Nhãn trang/đổi "Đối tác" → "Tổ gia công".
  - `default_subcontract_vendor_name` lấy theo `GcPartner` (qua `default_subcontract_partner_id`) thay cho `SxWorkCenter.is_subcontract`.
  - Migration dữ liệu `0155_gc_merge_work_center`: tạo GcPartner từ SxWorkCenter tick GC (dedup theo tên — thực tế 11 tổ đã được 0152 seed nên không trùng), gán partner cho phiếu cũ thiếu partner, rồi bỏ cờ `is_subcontract` trên các work center đó.
  - Giữ nguyên cột `SxWorkCenter.is_subcontract` và `SxSubcontractOrder.work_center` (ngừng dùng, không xóa — theo quyết định). Bỏ ô "Tổ thuê gia công" khỏi form Năng lực SX.
- **Reason**: Người dùng muốn một khái niệm duy nhất "Tổ gia công" mang đủ tính chất (đơn vị kế hoạch + tài khoản + giá + KPI + duyệt).
- **Source**: `san_xuat/migrations/0155_gc_merge_work_center.py`, `san_xuat/views_gc.py`, `san_xuat/views_gc_partner.py`, `san_xuat/forms_gc_partner.py::GcPartnerForm`, `san_xuat/services/phase3.py::default_subcontract_vendor_name`, `san_xuat/list_grid.py`, `templates/includes/portal_sidebar.html`, templates `gc_partner_list/detail`, `capacity_form.html`
- **Agent impact**: "Tổ gia công" = `GcPartner`, KHÔNG phải `SxWorkCenter`. Phiếu GC gắn `partner` + `team_slug`; `work_center` chỉ là liên kết phụ không load-bearing. Năng lực SX không còn tổ GC.

### 2026-11-02 — ui / menu Gia Công theo rule san-xuat-ui

- **Type**: feature (UI)
- **Change**: Mọi danh sách Gia Công dùng grid chuẩn Kho NPL (sắp xếp, đổi rộng, menu **Cột**): spec mới `gc_team`, `gc_partner`, `gc_account`, `gc_output`, `subcontract` (viết lại) trong `san_xuat/list_grid.py`. Topbar chuẩn `jp-npl-mat-topbar … w-100` cho Đối tác, Chi tiết đối tác, Duyệt sản lượng (bỏ `jp-page-header` + `btn-outline`). Bỏ đoạn mô tả / `form-text`. Style + hiệu ứng chung `san_xuat/templates/san_xuat/includes/gc_ui_styles.html` (thẻ số liệu, badge, thanh tiến độ, xuất hiện lần lượt; tắt khi `prefers-reduced-motion`). Bộ lọc Thuê GC có preset khoảng ngày (`Mọi thời gian` mặc định để không ẩn phiếu). `subcontract` submenu bỏ `perm_label` dài (đang bị dùng làm tiêu đề tab trình duyệt).
- **Source**: `san_xuat/list_grid.py`, `san_xuat/views_gc.py`, `san_xuat/views_gc_partner.py`, templates `subcontract_list`, `gc_*`, `includes/gc_kpi_cards.html`, `includes/gc_ui_styles.html`
- **Agent impact**: Trang Gia Công mới: bọc `jp-gc-page`, include `gc_ui_styles.html`; danh sách phải dùng `sx_list_grid_context(request, '<gc_key>')` + `sx_list_grid_head.html` + `sx_list_grid_scripts.html`.

### 2026-11-02 — workflow / cổng đối tác pn: Gửi đối tác, nhận/từ chối, KPI 4 chỉ tiêu

- **Type**: workflow | feature | schema
- **Change**:
  - Phiếu GC chỉ hiện trên pn sau khi nội bộ bấm **Gửi đối tác** (`services/gc_output.send_to_partner`, bắt buộc có LSX). Có **Thu hồi** khi đối tác chưa báo SL. Đổi đối tác trên phiếu đã gửi bị chặn (`phase3.update_subcontract_order`).
  - Đối tác: **Nhận đơn / Từ chối (bắt buộc lý do)**, chỉ tài khoản Chủ (`auth.is_owner`). Từ chối → phiếu rời pn, nội bộ thấy lý do, có thể Gửi lại. NV chỉ báo SL; không thấy giá/KPI.
  - Báo SL **được vượt từng size và tổng phiếu**; tiền = đơn giá × SL QC duyệt (`qty_received` có thể > `qty`). Tiến độ LSX vẫn chỉ cộng tới phần còn lại của size (trang duyệt hiện "Ghi tiến độ x" khi khác SL duyệt). Size gửi lên phải thuộc danh sách size của phiếu.
  - Hủy báo cáo không xóa: `GcOutputReport.STATUS_CANCELLED` + `cancelled_at/by`.
  - Duyệt giữ 1 cấp (QC nội bộ).
  - Nhật ký `GcPartnerActivity` (đăng nhập/sai/đăng xuất/đổi MK/nhận/từ chối/báo/hủy, IP proxy, UA) hiện ở chi tiết đối tác. Giới hạn đăng nhập sai theo IP (20 lần / 15 phút, cache). Mọi lỗi đăng nhập cùng một thông báo.
  - KPI (`services/gc_kpi.py`): Chất lượng 40%, Đúng hạn 30%, Đạt kế hoạch 20%, Phản hồi đơn ≤ 24h 10%; chỉ tiêu thiếu dữ liệu chia lại trọng số; hạng A ≥ 90 / B ≥ 75 / C. Chốt tháng `GcKpiSnapshot` (trang nội bộ `/san-xuat/gia-cong/kpi/`), `kpi_for_display` trả bản chốt nếu có.
  - pn thêm `/bang-gia/` (đơn giá đã duyệt đang hiệu lực), KPI trang `/bao-cao/`, giá + thành tiền trên chi tiết đơn (Chủ). 404/500 riêng cho urlconf pn (template 404 nội bộ dùng URL không có trên pn).
  - Migration `san_xuat/0154_gc_partner_send_kpi.py` (điền `partner_sent_at` cho phiếu đối tác đã nhận / đã báo SL / không còn nháp).
- **Reason**: Theo phân tích đã duyệt (Q1a, Q2–Q5, Q6); Q7–Q10 (thưởng/phạt, đối soát, thông báo, NPL trên pn) tạm hoãn.
- **Source**: `san_xuat/services/gc_output.py`, `san_xuat/services/gc_kpi.py`, `san_xuat/partner_portal/{views,auth,activity,urls}.py`, `san_xuat/partner_models.py`, `san_xuat/hub_models.py::SxSubcontractOrder.partner_*`, `san_xuat/views_gc.py::gc_kpi`, `san_xuat/views_hub.py::subcontract_detail`, `san_xuat/tests/test_partner_portal.py`
- **Agent impact**: `partner_orders()` lọc `partner_sent_at__isnull=False` — đừng tạo đường cho đối tác thấy phiếu chưa gửi. Không chặn SL báo theo SL phiếu nữa. Test DB mới hỏng ở migration dữ liệu cũ (`thiet_ke_sp/0025`, `kho_npl/0016`, `0019` gọi code runtime); chạy test với settings có `DATABASES[...]['TEST']['MIGRATE'] = False`.

### 2026-11-02 — workflow / menu Gia Công tách khỏi KHSX

- **Type**: feature | workflow
- **Change**:
  - Nhóm sidebar **Gia Công** có 6 mục, mỗi mục URL riêng dưới `/san-xuat/gia-cong/`: Thuê gia công (`/`, view `views_gc.subcontract_list` — trang riêng, không còn redirect sang `plan_board?tab=subcontract`), Tổ gia công (`to/`, `to/them/`, `to/<id>/`), Đối tác (`doi-tac/`), Tài khoản đối tác (`tai-khoan/`), Thống kê (`thong-ke/`, theo đối tác / tổ / đơn hàng), Duyệt kiểm kê / sản lượng (`duyet-san-luong/`).
  - Tổ thuê gia công (`SxWorkCenter.is_subcontract`) chỉ quản lý ở Gia Công: Năng lực SX ẩn tổ GC, bỏ checkbox "Tổ thuê gia công", `capacity_edit` của tổ GC redirect sang `gc_team_edit`.
  - `plan_board` GET `tab=subcontract` → redirect `/san-xuat/gia-cong/` (giữ q/date/status/team; `gc=<id>` → chi tiết). Đã gỡ nhánh dữ liệu + bảng GC trong `plan_board`. Bỏ link trùng "Kế hoạch sản xuất" (tab=subcontract) trong nhóm Kế hoạch SX.
  - Menu quyền `subcontract` đăng ký lại trong `MODULE_SUBMENUS` (nhãn "Gia Công", mục riêng trong ma trận quyền). Alias `subcontract → plan_board/plan` giữ nguyên nên người làm KHSX không mất quyền. `resolve_menu_from_request` map `/san-xuat/ke-hoach/bang/?tab=subcontract` → `subcontract`. Xóa rule thừa `/san-xuat/thue-gia-cong → plan_board`.
  - Chi tiết phiếu GC: quyền Sửa/In menu `subcontract` cũng được sửa/in phiếu.
- **Reason**: Menu Gia Công trước đây dẫn về URL/quyền/menu-active của Kế hoạch SX; người chỉ có quyền Gia công bị chặn với thông báo "Kế hoạch sản xuất".
- **Source**: `san_xuat/views_gc.py`, `san_xuat/services/gc_stats.py`, `san_xuat/urls.py`, `san_xuat/views_hub.py::plan_board/_redirect_legacy_subcontract_tab/capacity_list/capacity_edit/subcontract_detail`, `templates/includes/portal_sidebar.html`, `hrm/submenu_registry.py`, `hrm/menu_permissions.py`, `hrm/forms.py::SAN_XUAT_PERMISSION_SECTIONS`
- **Agent impact**: Không tạo link mới tới `plan_board?tab=subcontract`; dùng `san_xuat:subcontract_list`. Màn GC mới đặt trong `views_gc.py`, quyền dùng `_can_view/_can_edit` của `views_gc_partner.py`.

### 2026-10-31 — feature / gc-partner-gd2 (Cổng đối tác pn.justplay.vn)

- **Type**: feature | architecture | workflow
- **Change**: Giai đoạn 2 cổng đối tác gia công.
  - Model `GcOutputReport` (báo sản lượng ngày × size, trạng thái submitted/approved/rejected, SL duyệt, progress_posted).
  - Field `SxSubcontractOrder.partner_accepted_at`.
  - Service `gc_output.py`: submit/cancel/approve/reject/unapprove báo cáo; tự động cộng tiến độ tổ thuê khi QC duyệt, trừ lại khi huỷ duyệt; tự hoàn thành phiếu khi đủ SL.
  - Service `gc_kpi.py`: thống kê KPI đối tác theo tháng (SL duyệt, tỉ lệ QC, đúng hạn, thành tiền, biểu đồ ngày).
  - Service `subcontract_progress.py`: thêm `team_size_status`, `post_report_progress`, `revert_report_progress`.
  - `phase3.py`: bỏ qua `post_gc_progress` tổng nếu phiếu đã có báo cáo được duyệt; chặn huỷ nhận khi có báo cáo đã duyệt.
  - Middleware `PartnerPortalHostMiddleware` route host pn.* sang urlconf riêng `san_xuat.partner_portal.urls`.
  - Auth backend tách biệt (`partner_portal/auth.py`): session lưu account_id + hash mật khẩu, lockout sau 5 lần sai, force đổi mật khẩu lần đầu.
  - Partner portal views: login, logout, change_password, home (danh sách đơn), order_detail (nhận đơn + báo SL), reports (KPI chủ ĐT).
  - Internal view `gc_output_review` + template: QC duyệt/từ chối/huỷ duyệt báo cáo SL, nhập SL duyệt theo size.
  - Settings: `PARTNER_PORTAL_DOMAIN`, `PARTNER_PORTAL_HOSTS` tự thêm vào ALLOWED_HOSTS.
  - Migration `0153_gc_output_report.py`.
- **Reason**: Đối tác cần portal riêng để nhận đơn và báo sản lượng; QC nội bộ duyệt trước khi ghi tiến độ.
- **Source**: `san_xuat/partner_portal/`, `san_xuat/services/gc_output.py`, `san_xuat/services/gc_kpi.py`, `san_xuat/views_gc_partner.py`, `PortalJustPlay/settings.py`
- **Agent impact**: Host `pn.*` dùng urlconf `san_xuat.partner_portal.urls` (không phải ROOT_URLCONF); auth partner dùng `request.gc_account` thay vì `request.user`; middleware nội bộ (DepartmentModuleAccess, AttendancePunchGate...) thấy AnonymousUser trên host pn nên tự cho qua.

### 2026-10-31 — schema+workflow / gc-partner-gd1

- **Change**: Đối tác gia công (GĐ1).
  - Model mới trong `san_xuat/partner_models.py`: `GcPartner` (danh mục đối tác + công đoạn nhận + năng lực), `GcPartnerAccount` (**bảng tài khoản riêng**, không phải `auth.User`; mật khẩu băm Django, bắt buộc đổi lần đầu, có trường khóa/sai MK cho cổng `pn`), `GcPriceRule` (giá theo đối tác × công đoạn × mã SP, trống = giá chung; nháp → duyệt; hiệu lực từ/đến; chặn trùng hiệu lực khi duyệt).
  - `SxSubcontractOrder.partner` (FK PROTECT). Migration 0152 backfill đối tác từ tổ GC `is_subcontract` + `vendor_name` phiếu cũ.
  - Form tạo/sửa phiếu GC chọn **Đối tác** thay cho tổ GC. `vendor_name` = tên đối tác (giữ cho các màn cũ). Đơn giá trống/0 → lấy giá đã duyệt hiệu lực ngày phiếu (`gc_partner.resolve_gc_price`); giá được chốt vào phiếu.
  - Màn `/san-xuat/thue-gia-cong/doi-tac/` (+ chi tiết): CRUD đối tác, tạo/khóa/reset MK tài khoản, bảng giá + duyệt, thống kê phiếu. Có nút vào từ tab Thuê gia công trên KHSX.
- **Reason**: Nền cho cổng đối tác `pn.justplay.vn` (GĐ2: đăng nhập, nhận đơn, báo SL; QC duyệt).
- **Source**: `san_xuat/partner_models.py`, `services/gc_partner.py`, `forms_gc_partner.py`, `views_gc_partner.py`, `services/phase3.py` (`_apply_partner`, `_resolve_unit_price`, `default_subcontract_partner_id`), `forms_phase3.py`, `views_hub.py::subcontract_create/detail`, templates `gc_partner_list.html`, `gc_partner_detail.html`, `includes/gc_partner_form_fields.html`, migration `0152_gc_partner`.
- **Agent impact**:
  - Quyền: xem/sửa theo menu `subcontract` / `plan_board`. Duyệt, xóa hoặc kết thúc giá đã duyệt cần `is_staff` hoặc quyền delete menu `subcontract`. Cổng `pn.justplay.vn` đã có route, auth riêng, báo SL và KPI; QC duyệt tại `gc_output_review` mới ghi tiến độ.
  - Không tạo `User` cho đối tác. Phiên đăng nhập `pn` (GĐ2) phải dùng `GcPartnerAccount.check_password`.
  - `subcontract_vendor_choices` / `default_subcontract_vendor_name` không còn dùng trên form, nhưng vẫn được giữ lại.

### 2026-10-31 — workflow / subcontract-progress-gd0

- **Change**: Thuê GC (GĐ0, nền cho cổng đối tác `pn.justplay.vn`).
  - Nhận hàng GC giờ **ghi SL nhận vào tiến độ tổ Ob thuê**, vào ngày nhận. SL được chia theo phần còn lại từng size, ghi qua `set_team_day_qtys` và log `SxTeamProgressLog.kind='gc'` (nhãn «Nhận GC»).
  - **Phiếu tách ngày** (`plan_date`) chỉ đóng tổ khi tổ đã đủ SL. Phiếu cả công đoạn vẫn đóng ngay.
  - Huỷ nhận trừ đúng phần đã cộng (`progress_posted`/`progress_date`) và chỉ mở lại tổ nếu tổ đang đóng.
  - Thêm `SxSubcontractOrder.unit_price` (nhập ở form tạo/sửa). Khi nhận: `service_fee = unit_price × qty_received`, lên giá thành thực tế. Đơn giá = 0 thì giữ `service_fee` cũ.
- **Reason**: Trước đây nhận một phần tách GC đóng cả tổ trên LSX, và SL GC không lên lộ trình/tiến độ. `service_fee` không có chỗ nhập.
- **Source**: `san_xuat/services/subcontract_progress.py`, `san_xuat/services/phase3.py::_close_ob_team_for_gc`, `receive_subcontract_goods`, `undo_receive_subcontract_goods`, `advance_subcontract_order`, `create_subcontract_order`, `update_subcontract_order`; migration `san_xuat/0151_subcontract_price_progress`; `forms_phase3.py::SubcontractCreateForm`, `SubcontractUpdateForm`; `subcontract_create.html`, `subcontract_detail.html`.
- **Agent impact**:
  - SL GC chỉ nằm trong `SxProductionStat` của tổ thuê (team_label theo tổ). Đừng cộng thêm `qty_received` khi tính tiến độ.
  - Dữ liệu cũ (nhận trước 0151) không có `progress_posted`, nên huỷ nhận sẽ không trừ SL.
  - Phiếu GC chỉ gắn SO (chưa có LSX) không ghi tiến độ cho tới khi gắn LSX.
  - Nhận GC chưa trừ/nhập kho NPL (giữ nguyên hành vi cũ).

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

### 2026-11-06 — architecture / static architecture map

- **Type**: architecture | feature
- **Change**: Thêm command `python manage.py architecture_map` kết hợp Django introspection và AST để sinh app/URL/model-table/function/call hints, Mermaid và trang HTML tìm kiếm local.
- **Reason**: Giúp truy vết chức năng, bảng liên quan và phạm vi cần kiểm tra trước khi sửa code.
- **Source**: `tools/architecture/ast_scanner.py`, `tools/management/commands/architecture_map.py`, `docs/architecture/README.md`.
- **Agent impact**: Đây là bản đồ tĩnh bổ trợ; vẫn dùng CodeGraph để xác minh callers/callees/impact và runtime tracing để xác nhận SQL thực tế.

## Template cho entry mới

```markdown
### YYYY-MM-DD — type

- **Change**:
- **Reason**:
- **Source**:
- **Agent impact**:
```

Không sửa hoặc xoá entry lịch sử để phản ánh thay đổi mới. Cập nhật tài liệu hiện tại trong `docs/AI_CODEBASE_MAP.md`, sau đó thêm entry mới ở đây.
