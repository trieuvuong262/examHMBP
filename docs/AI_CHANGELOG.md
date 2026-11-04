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

### 2026-11-04 — feature / tài khoản demo chỉ xem

- **Type**: feature | workflow
- **Change**: Thêm `ReadOnlyAccountMiddleware` (sau `DepartmentModuleAccessMiddleware`) áp dụng cho username trong `hrm/user_search.py::READ_ONLY_USERNAMES` (`demo`). Tài khoản này không được thêm/sửa/xóa/in/xuất/tải về/đổi hoặc đặt lại mật khẩu, không vào được DS nhân sự, và bị ẩn khỏi DS nhân sự, file export, sơ đồ tổ chức và ô chọn người (`HIDDEN_HRM_LIST_USERNAMES`). Không bị ép chấm công. Không bao giờ được chọn làm người duyệt (`find_manager_with_subordinate`) và không làm phòng có thêm bước duyệt Trưởng phòng (`department_has_department_heads_extended`). `_PROTECTED_USERNAMES` vẫn chỉ gồm `admin`.
- **Reason**: Cần tài khoản demo cho khách xem portal với phạm vi quyền Trưởng phòng IT nhưng không thể thay đổi dữ liệu.
- **Source**: `PortalJustPlay/middleware.py::ReadOnlyAccountMiddleware`; `PortalJustPlay/settings.py::MIDDLEWARE`; `hrm/user_search.py::is_read_only_account`; `zalo/password_reset.py::resolve_user_for_password_reset`; `zalo/email_password_reset.py::_user_can_reset`; `cham_cong/services.py::_should_force_punch`; test `hrm/tests_read_only_account.py`.
- **Agent impact**: Thêm tài khoản chỉ xem mới = thêm username vào `READ_ONLY_USERNAMES`. Middleware chặn GET theo token của `url_name`; URL thao tác mới nên đặt tên chứa động từ (`*_delete`, `*_export`, `*_print`, `*_edit`…) để được chặn tự động. Nhóm quyền của demo là `PermissionGroup` riêng; lệnh `grant_export_print` bật export/print cho mọi nhóm nhưng middleware vẫn chặn.

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

## Template cho entry mới

```markdown
### YYYY-MM-DD — type

- **Change**:
- **Reason**:
- **Source**:
- **Agent impact**:
```

Không sửa hoặc xoá entry lịch sử để phản ánh thay đổi mới. Cập nhật tài liệu hiện tại trong `docs/AI_CODEBASE_MAP.md`, sau đó thêm entry mới ở đây.
