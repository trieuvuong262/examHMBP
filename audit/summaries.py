"""
Sinh mô tả chi tiết cho nhật ký thao tác — theo URL, nút bấm, dữ liệu form.
"""

from django.http import HttpRequest

from audit.models import UserActivityLog

# Nhãn tiếng Việt cho field form thường gặp
FIELD_LABELS: dict[str, str] = {
    'full_name': 'Họ tên',
    'username': 'Tài khoản',
    'employee_code': 'Mã NS',
    'email': 'Email',
    'phone': 'SĐT',
    'role': 'Vai trò',
    'department': 'Phòng ban',
    'department_id': 'Phòng ban',
    'division': 'Bộ phận',
    'division_id': 'Bộ phận',
    'job_position': 'Chức danh',
    'position': 'Chức danh',
    'title': 'Tiêu đề',
    'name': 'Tên',
    'subject': 'Tiêu đề',
    'content': 'Nội dung',
    'description': 'Mô tả',
    'status': 'Trạng thái',
    'category': 'Danh mục',
    'category_id': 'Nhóm tài liệu',
    'course_id': 'Khóa học',
    'exam_id': 'Bài kiểm tra',
    'lesson_id': 'Bài học',
    'chapter_id': 'Chương',
    'candidate_id': 'Ứng viên',
    'kpi_id': 'KPI',
    'year': 'Năm',
    'period': 'Kỳ',
    'tab': 'Tab',
    'is_active': 'Kích hoạt',
    'is_employed': 'Đang làm việc',
    'gender': 'Giới tính',
    'date_of_birth': 'Ngày sinh',
    'start_date': 'Ngày bắt đầu',
    'end_date': 'Ngày kết thúc',
    'sort_order': 'Thứ tự',
    'modules': 'Module menu',
    'module_permissions': 'Quyền module',
    'new_status': 'Trạng thái mới',
    'note': 'Ghi chú',
    'hr_note': 'Ghi chú HR',
    'interview_date': 'Ngày phỏng vấn',
    'interview_time': 'Giờ phỏng vấn',
    'score': 'Điểm',
    'answer': 'Câu trả lời',
    'question_text': 'Câu hỏi',
    'slug': 'Đường dẫn',
    'file': 'Tệp đính kèm',
    'document': 'Tài liệu',
    'video_url': 'Video',
    'is_published': 'Xuất bản',
    'priority': 'Ưu tiên',
    'announcement_type': 'Loại thông báo',
}

# Nút submit / intent trong form
SUBMIT_BUTTON_LABELS: dict[str, str] = {
    'save': 'Lưu',
    'submit': 'Gửi',
    'create': 'Tạo mới',
    'update': 'Cập nhật',
    'delete': 'Xóa',
    'confirm': 'Xác nhận',
    'approve': 'Duyệt',
    'reject': 'Từ chối',
    'export': 'Xuất Excel',
    'import': 'Nhập Excel',
    'reset': 'Đặt lại',
    'publish': 'Xuất bản',
    'unpublish': 'Gỡ xuất bản',
    'toggle': 'Bật/tắt',
    'grade': 'Chấm điểm',
    'complete': 'Hoàn thành',
    'copy': 'Sao chép',
    'download': 'Tải xuống',
    'upload': 'Tải lên',
    'send': 'Gửi',
    'apply': 'Áp dụng',
    'filter': 'Lọc',
    'search': 'Tìm kiếm',
}

# url_name → mô tả theo method (GET=xem/mở, POST=thao tác)
# Placeholder {key} lấy từ resolver kwargs
URL_DESCRIPTIONS: dict[str, dict[str, str] | str] = {
    # Portal
    'home_portal': 'xem trang chủ portal',
    'login_redirect': 'chuyển hướng sau đăng nhập',
    'password_change': {
        'GET': 'mở form đổi mật khẩu',
        'POST': 'đổi mật khẩu tài khoản',
    },
    'password_change_done': 'xem trang đổi mật khẩu thành công',
    'logout': 'bấm nút Đăng xuất',
    'user_guide': 'xem hướng dẫn sử dụng',
    'user_guide_edit': {
        'GET': 'mở form chỉnh sửa hướng dẫn',
        'POST': 'lưu nội dung hướng dẫn sử dụng',
    },

    # HRM — Nhân sự
    'user_list': 'xem danh sách nhân viên',
    'user_add': {
        'GET': 'mở form thêm nhân viên mới',
        'POST': 'tạo nhân viên mới',
    },
    'user_edit': {
        'GET': 'mở form sửa nhân viên #{user_id}',
        'POST': 'cập nhật thông tin nhân viên #{user_id}',
    },
    'user_delete': 'xóa nhân viên #{user_id}',
    'user_password_reset': 'đặt lại mật khẩu nhân viên #{user_id}',
    'user_toggle_employed': 'bật/tắt trạng thái làm việc nhân viên #{user_id}',
    'user_import_excel': {
        'GET': 'mở form nhập Excel nhân viên',
        'POST': 'nhập danh sách nhân viên từ Excel',
    },
    'user_export_excel': 'xuất danh sách nhân viên ra Excel',
    'user_download_template': 'tải file mẫu Excel nhân viên',
    'org_structure': 'xem cơ cấu tổ chức',
    'department_list': 'xem danh sách phòng ban',
    'department_add': {
        'GET': 'mở form thêm phòng ban',
        'POST': 'tạo phòng ban mới',
    },
    'department_edit': {
        'GET': 'mở form sửa phòng ban #{pk}',
        'POST': 'cập nhật phòng ban #{pk}',
    },
    'department_delete': 'xóa phòng ban #{pk}',
    'department_permissions': {
        'GET': 'xem/mở cấu hình phân quyền phòng ban #{pk}',
        'POST': 'lưu phân quyền menu phòng ban #{pk}',
    },
    'division_add': {
        'GET': 'mở form thêm bộ phận',
        'POST': 'tạo bộ phận mới',
    },
    'division_edit': {
        'GET': 'mở form sửa bộ phận #{pk}',
        'POST': 'cập nhật bộ phận #{pk}',
    },
    'division_delete': 'xóa bộ phận #{pk}',
    'permission_config': 'xem trang cấu hình phân quyền hệ thống',
    'role_permission_edit': {
        'GET': 'mở cấu hình quyền vai trò {role}',
        'POST': 'lưu quyền vai trò {role}',
    },

    # Kiểm tra
    'admin_dashboard': 'xem dashboard quản trị',
    'exam_list': 'xem danh sách bài kiểm tra',
    'exam_create': {
        'GET': 'mở form tạo bài kiểm tra',
        'POST': 'tạo bài kiểm tra mới',
    },
    'exam_edit': {
        'GET': 'mở form sửa bài kiểm tra #{pk}',
        'POST': 'cập nhật bài kiểm tra #{pk}',
    },
    'exam_delete': 'xóa bài kiểm tra #{pk}',
    'take_exam': {
        'GET': 'mở bài kiểm tra #{exam_id}',
        'POST': 'nộp bài kiểm tra #{exam_id}',
    },
    'question_add': 'thêm câu hỏi vào bài kiểm tra #{exam_id}',
    'question_edit_detail': 'sửa câu hỏi #{question_id} (bài #{exam_id})',
    'question_remove': 'xóa câu hỏi #{question_id} (bài #{exam_id})',
    'admin_results': 'xem kết quả bài kiểm tra',
    'grade_submission': {
        'GET': 'mở form chấm bài #{submission_id}',
        'POST': 'chấm điểm bài làm #{submission_id}',
    },
    'competency_add_ajax': 'thêm năng lực (AJAX)',
    'competency_delete_ajax': 'xóa năng lực #{pk} (AJAX)',

    # Thông báo
    'list': 'xem danh sách thông báo',
    'detail': 'xem chi tiết thông báo #{pk}',
    'admin_list': 'xem quản trị thông báo',
    'admin_create': {
        'GET': 'mở form tạo thông báo',
        'POST': 'đăng thông báo mới',
    },
    'admin_edit': {
        'GET': 'mở form sửa thông báo #{pk}',
        'POST': 'cập nhật thông báo #{pk}',
    },
    'admin_delete': 'xóa thông báo #{pk}',

    # Đào tạo
    'training_home': 'xem trang đào tạo',
    'my_courses': 'xem khóa học của tôi',
    'course_start': 'mở khóa học #{course_id}',
    'learning_space': 'học bài #{lesson_id} (khóa #{course_id})',
    'mark_lesson_complete': 'đánh dấu hoàn thành bài #{lesson_id}',
    'course_list': 'xem danh sách khóa học (quản trị)',
    'course_create': {
        'GET': 'mở form tạo khóa học',
        'POST': 'tạo khóa học mới',
    },
    'course_edit': {
        'GET': 'mở form sửa khóa học #{course_id}',
        'POST': 'cập nhật khóa học #{course_id}',
    },
    'course_builder': 'mở trình dựng nội dung khóa #{course_id}',
    'chapter_create': 'thêm chương cho khóa #{course_id}',
    'lesson_create': 'thêm bài học vào chương #{chapter_id}',
    'lesson_edit': {
        'GET': 'mở form sửa bài học #{lesson_id}',
        'POST': 'cập nhật bài học #{lesson_id}',
    },
    'lesson_delete': 'xóa bài học #{lesson_id}',
    'update_lesson_order': 'sắp xếp lại thứ tự bài học',
    'api_get_categories': 'tải danh mục khóa học (API)',
    'api_add_category': 'thêm danh mục khóa học (API)',
    'api_edit_category': 'sửa danh mục khóa học #{pk} (API)',
    'api_delete_category': 'xóa danh mục khóa học #{pk} (API)',

    # Tuyển dụng
    'kanban_board': 'xem bảng Kanban tuyển dụng',
    'update_candidate_status': 'cập nhật trạng thái ứng viên (kéo thả Kanban)',
    'add_candidate': {
        'GET': 'mở form thêm ứng viên',
        'POST': 'thêm ứng viên mới',
    },
    'job_posting_list': 'xem danh sách tin tuyển dụng',
    'job_posting_create': {
        'GET': 'mở form tạo tin tuyển dụng',
        'POST': 'đăng tin tuyển dụng mới',
    },
    'job_posting_edit': {
        'GET': 'mở form sửa tin #{pk}',
        'POST': 'cập nhật tin tuyển dụng #{pk}',
    },
    'job_posting_delete': 'xóa tin tuyển dụng #{pk}',
    'convert_to_employee': 'chuyển ứng viên #{candidate_id} thành nhân viên',
    'candidate_detail_ajax': 'xem chi tiết ứng viên #{pk}',
    'update_hr_note': 'cập nhật ghi chú HR ứng viên',
    'set_interview_schedule': 'đặt lịch phỏng vấn ứng viên',
    'get_all_interviews': 'xem danh sách lịch phỏng vấn',
    'get_candidate_interview': 'xem lịch phỏng vấn ứng viên #{pk}',
    'update_practice_license': 'cập nhật giấy phép hành nghề',
    'get_candidate_license': 'xem giấy phép hành nghề ứng viên #{pk}',
    'get_all_licenses': 'xem danh sách giấy phép hành nghề',
    'export_interviews_excel': 'xuất Excel lịch phỏng vấn',
    'export_licenses_excel': 'xuất Excel giấy phép hành nghề',

    # KPI
    'kpi_list': 'xem danh sách KPI',
    'kpi_detail': 'xem chi tiết KPI #{kpi_id}',
    'yearly_kpi_create': {
        'GET': 'mở form tạo KPI năm',
        'POST': 'tạo KPI năm mới',
    },
    'kpi_import_excel': {
        'GET': 'mở form nhập KPI từ Excel',
        'POST': 'nhập dữ liệu KPI từ Excel',
    },
    'download_kpi_sample_excel': 'tải file mẫu Excel KPI',

    # Báo cáo
    'hub': 'xem trung tâm báo cáo',
    'today': {
        'GET': 'xem/mở báo cáo công việc hôm nay',
        'POST': 'lưu báo cáo công việc hôm nay',
    },
    'copy_yesterday': 'sao chép báo cáo từ hôm qua',
    'my': 'xem báo cáo của tôi',
    'team': 'xem báo cáo nhóm',

    # Tài liệu
    'browse': 'xem thư viện tài liệu',
    'browse_category': 'xem nhóm tài liệu {category_slug}',
    'browse_document': 'mở tài liệu {doc_slug}',
    'admin_hub': 'xem quản trị tài liệu',
    'admin_categories': 'xem danh sách nhóm tài liệu',
    'admin_category_create': {
        'GET': 'mở form thêm nhóm tài liệu',
        'POST': 'tạo nhóm tài liệu mới',
    },
    'admin_category_edit': {
        'GET': 'mở form sửa nhóm tài liệu #{pk}',
        'POST': 'cập nhật nhóm tài liệu #{pk}',
    },
    'admin_category_delete': 'xóa nhóm tài liệu #{pk}',
    'admin_documents': 'xem danh sách tài liệu (quản trị)',
    'admin_document_create': {
        'GET': 'mở form thêm tài liệu',
        'POST': 'tải lên/tạo tài liệu mới',
    },
    'admin_document_edit': {
        'GET': 'mở form sửa tài liệu #{pk}',
        'POST': 'cập nhật tài liệu #{pk}',
    },
    'admin_document_delete': 'xóa tài liệu #{pk}',

    # Nhật ký
    'log_list': 'xem danh sách nhật ký thao tác',
    'log_detail': 'xem chi tiết nhật ký #{pk}',
    'user_timeline': 'xem timeline thao tác user #{user_id}',

    # HRM bổ sung
    'permission_group_add': {
        'GET': 'mở form thêm nhóm quyền',
        'POST': 'tạo nhóm quyền mới',
    },
    'permission_group_edit': {
        'GET': 'mở form sửa nhóm quyền #{pk}',
        'POST': 'cập nhật nhóm quyền #{pk}',
    },
    'permission_group_delete': 'xóa nhóm quyền #{pk}',
    'org_position_add': {
        'GET': 'mở form thêm chức danh',
        'POST': 'tạo chức danh mới',
    },
    'org_position_edit': {
        'GET': 'mở form sửa chức danh #{pk}',
        'POST': 'cập nhật chức danh #{pk}',
    },
    'org_position_delete': 'xóa chức danh #{pk}',
    'user_nas_folders': {
        'GET': 'xem quyền thư mục NAS nhân viên #{user_id}',
        'POST': 'lưu quyền thư mục NAS nhân viên #{user_id}',
    },
    'update_avatar': {
        'GET': 'mở form đổi ảnh đại diện',
        'POST': 'cập nhật ảnh đại diện',
    },

    # Tài liệu bổ sung
    'qa': 'mở trợ lý hỏi đáp thư viện tài liệu',
    'qa_ask': 'đặt câu hỏi thư viện tài liệu (AI)',
    'qa_suggest_initial': 'gợi ý câu hỏi thư viện tài liệu',
    'admin_qa_settings': {
        'GET': 'mở cấu hình Q&A thư viện',
        'POST': 'lưu cấu hình Q&A thư viện',
    },
    'file_view': 'xem file tài liệu',
    'file_download': 'tải file tài liệu',
}

# url_name trùng giữa app — tra theo prefix path (namespace:url_name)
PATH_PREFIXES: tuple[tuple[str, str], ...] = (
    ('/nhat-ky/', 'audit'),
    ('/kiotviet/', 'kiotviet'),
    ('/thiet-bi/', 'equipment'),
    ('/cong-viec/', 'tasks'),
    ('/yeu-cau/', 'service_requests'),
    ('/gop-y/', 'feedback'),
    ('/thu-muc-nas/', 'nas'),
    ('/cong-cu/', 'tools'),
    ('/tai-lieu/', 'documents'),
    ('/reports/', 'reports'),
    ('/announcements/', 'announcements'),
)

NAMESPACE_URL_DESCRIPTIONS: dict[str, dict[str, str] | str] = {
    # Audit / quản trị hệ thống
    'audit:backup_page': 'xem trang backup Portal lên NAS',
    'audit:backup_run': 'bấm chạy backup Portal lên NAS',
    'audit:kiotviet_sync': 'xem trang đồng bộ KiotViet',
    'audit:kiotviet_sync_save': {
        'POST': 'lưu cấu hình lịch đồng bộ KiotViet',
    },
    'audit:kiotviet_sync_run': {
        'POST': 'chạy đồng bộ KiotViet thủ công',
    },
    'audit:kiotviet_sync_status': 'xem tiến độ job đồng bộ KiotViet #{job_id}',
    'audit:nas_links': {
        'GET': 'xem trang cập nhật link NAS',
        'POST': 'lưu cấu hình link NAS',
    },

    # KiotViet tra cứu
    'kiotviet:customer_lookup': 'tra cứu khách hàng KiotViet',
    'kiotviet:customer_detail': 'xem chi tiết khách hàng KiotViet #{customer_id}',
    'kiotviet:order_lookup': 'tra cứu đơn đặt hàng KiotViet',
    'kiotviet:order_detail': 'xem chi tiết đơn đặt hàng KiotViet #{order_id}',
    'kiotviet:invoice_lookup': 'tra cứu hóa đơn KiotViet',
    'kiotviet:invoice_detail': 'xem chi tiết hóa đơn KiotViet #{invoice_id}',
    'kiotviet:product_lookup': 'hàng hoá KiotViet',
    'kiotviet:product_detail': 'xem chi tiết sản phẩm KiotViet #{product_id}',
    'kiotviet:stock_lookup': 'tra cứu tồn kho KiotViet',
    'kiotviet:purchase_lookup': 'tra cứu phiếu nhập KiotViet',
    'kiotviet:purchase_detail': 'xem chi tiết phiếu nhập KiotViet #{purchase_id}',

    # Công việc
    'tasks:hub': 'xem trung tâm công việc',
    'tasks:my': 'xem công việc của tôi',
    'tasks:detail': 'xem chi tiết công việc #{pk}',
    'tasks:personal_hub': 'xem công việc cá nhân',
    'tasks:assigned': 'xem công việc được giao',
    'tasks:assign': {
        'GET': 'mở form giao việc',
        'POST': 'giao công việc mới',
    },
    'tasks:recurring': 'xem công việc lặp',
    'tasks:recurrence_action': 'thao tác công việc lặp',
    'tasks:reassign': 'chuyển giao công việc',
    'tasks:project_list': 'xem danh sách dự án',
    'tasks:project_create': {
        'GET': 'mở form tạo dự án',
        'POST': 'tạo dự án mới',
    },
    'tasks:project_detail': 'xem chi tiết dự án #{pk}',
    'tasks:project_step': 'cập nhật bước dự án #{pk}',
    'tasks:handoff': 'bàn giao bước dự án',
    'tasks:project_reassign': 'chuyển giao dự án',
    'tasks:cross_dept_list': 'xem dự án liên phòng ban',
    'tasks:cross_dept_create': {
        'GET': 'mở form tạo dự án liên phòng ban',
        'POST': 'tạo dự án liên phòng ban',
    },
    'tasks:cross_dept_pending': 'xem dự án liên phòng ban chờ xử lý',
    'tasks:cross_dept_detail': 'xem chi tiết dự án liên phòng ban #{pk}',
    'tasks:cross_dept_step': 'cập nhật bước dự án liên phòng ban',
    'tasks:cross_dept_claim': 'nhận xử lý dự án liên phòng ban',
    'tasks:cross_dept_handoff': 'bàn giao dự án liên phòng ban',
    'tasks:cross_dept_reassign': 'chuyển giao dự án liên phòng ban',

    # Yêu cầu / đề xuất / hỗ trợ
    'service_requests:hub': 'xem trung tâm yêu cầu dịch vụ',
    'service_requests:my': 'xem yêu cầu của tôi',
    'service_requests:detail': 'xem chi tiết yêu cầu #{pk}',
    'service_requests:create': {
        'GET': 'mở form tạo yêu cầu',
        'POST': 'gửi yêu cầu mới',
    },
    'service_requests:de_xuat_my': 'xem đề xuất của tôi',
    'service_requests:de_xuat_pending': 'xem đề xuất chờ duyệt',
    'service_requests:de_xuat_detail': 'xem chi tiết đề xuất #{pk}',
    'service_requests:ho_tro_hub': 'xem trung tâm hỗ trợ IT',
    'service_requests:ho_tro_my': 'xem phiếu hỗ trợ của tôi',
    'service_requests:ho_tro_pending': 'xem phiếu hỗ trợ chờ xử lý',
    'service_requests:ho_tro_detail': 'xem chi tiết phiếu hỗ trợ #{pk}',
    'service_requests:create_it_repair': {
        'POST': 'tạo phiếu sửa chữa IT',
    },
    'service_requests:create_it_repair_it': {
        'POST': 'tạo phiếu sửa chữa IT (phòng IT)',
    },
    'service_requests:create_it_repair_production': {
        'POST': 'tạo phiếu sửa chữa IT (sản xuất)',
    },
    'service_requests:catalog_list': 'xem danh mục tài sản đề xuất',
    'service_requests:catalog_create': {
        'GET': 'mở form thêm danh mục tài sản',
        'POST': 'thêm danh mục tài sản',
    },
    'service_requests:catalog_edit': {
        'GET': 'mở form sửa danh mục tài sản #{pk}',
        'POST': 'cập nhật danh mục tài sản #{pk}',
    },
    'service_requests:catalog_delete': 'xóa danh mục tài sản #{pk}',
    'service_requests:pending': 'xem yêu cầu chờ xử lý',

    # Góp ý
    'feedback:hub': 'xem trung tâm góp ý',
    'feedback:list': 'xem danh sách góp ý',
    'feedback:detail': 'xem chi tiết góp ý #{pk}',
    'feedback:create': {
        'GET': 'mở form gửi góp ý',
        'POST': 'gửi góp ý mới',
    },

    # NAS
    'nas:browse': 'duyệt thư mục NAS',
    'nas:share_create': {
        'POST': 'tạo link chia sẻ NAS',
    },
    'nas:share_open': 'mở link chia sẻ NAS',
    'nas:download': 'tải file từ NAS',
    'nas:delete': 'xóa file/thư mục trên NAS',

    # Công cụ
    'tools:pdf_to_word': {
        'GET': 'mở công cụ PDF sang Word',
        'POST': 'chuyển PDF sang Word',
    },
    'tools:ocr': {
        'GET': 'mở công cụ OCR',
        'POST': 'nhận dạng văn bản OCR',
    },
    'tools:compress_image': {
        'GET': 'mở công cụ nén ảnh',
        'POST': 'nén ảnh',
    },
    'tools:remove_background': {
        'GET': 'mở công cụ xóa nền ảnh',
        'POST': 'xóa nền ảnh',
    },
    'tools:qr_generator': {
        'GET': 'mở công cụ tạo mã QR',
        'POST': 'tạo mã QR',
    },
    'tools:notes': 'xem ghi chú nhanh',
    'tools:note_quick_add': 'thêm ghi chú nhanh',
    'tools:notes_api': 'API ghi chú',
    'tools:note_detail_api': 'API chi tiết ghi chú',
}

# Field ưu tiên hiển thị trong mô tả theo url_name
URL_POST_HIGHLIGHTS: dict[str, list[str]] = {
    'user_add': ['full_name', 'username', 'employee_code', 'department', 'role'],
    'user_edit': ['full_name', 'username', 'role', 'department', 'job_position'],
    'department_add': ['name', 'sort_order'],
    'department_edit': ['name', 'sort_order'],
    'department_permissions': ['modules'],
    'role_permission_edit': ['module_permissions'],
    'division_add': ['name', 'department'],
    'division_edit': ['name', 'department'],
    'admin_create': ['title', 'announcement_type', 'priority'],
    'admin_edit': ['title', 'announcement_type', 'priority'],
    'exam_create': ['title', 'duration', 'pass_score'],
    'exam_edit': ['title', 'duration', 'pass_score'],
    'course_create': ['title', 'description'],
    'course_edit': ['title', 'description'],
    'lesson_edit': ['title', 'chapter_id'],
    'job_posting_create': ['title', 'department', 'status'],
    'job_posting_edit': ['title', 'department', 'status'],
    'add_candidate': ['full_name', 'phone', 'email', 'position'],
    'update_candidate_status': ['candidate_id', 'new_status', 'status'],
    'admin_category_create': ['name', 'sort_order'],
    'admin_category_edit': ['name', 'sort_order'],
    'admin_document_create': ['title', 'category', 'category_id'],
    'admin_document_edit': ['title', 'category', 'category_id'],
    'today': ['date', 'lines', 'content'],
    'grade_submission': ['score', 'feedback'],
    'take_exam': ['exam_id'],
    'password_change': ['old_password'],
    'user_guide_edit': ['content', 'title'],
    'kiotviet_sync_save': ['interval_minutes', 'entities'],
    'kiotviet_sync_run': ['entities'],
    'permission_group_add': ['name'],
    'permission_group_edit': ['name'],
    'backup_run': [],
    'assign': ['title', 'assigned_to', 'due_date'],
    'create': ['title', 'subject', 'description'],
    'catalog_create': ['name', 'code'],
    'catalog_edit': ['name', 'code'],
    'project_create': ['title', 'name'],
    'cross_dept_create': ['title', 'name'],
    'device_edit': ['name', 'status', 'category'],
    'feedback_create': ['subject', 'content'],
}

SKIP_POST_KEYS = frozenset({
    'csrfmiddlewaretoken',
    'csrf_token',
    '_method',
    '_token',
    'next',
    'submit',
    'action',
    'client_hostname',
    'client_local_ip',
})


def _format_template(template: str, kwargs: dict) -> str:
    try:
        return template.format(**{k: v for k, v in kwargs.items()})
    except (KeyError, ValueError):
        return template


def _detect_submit_button(request: HttpRequest) -> str:
    post = getattr(request, 'POST', None)
    if not post:
        return ''
    for key in post:
        if key in SKIP_POST_KEYS:
            continue
        if key.lower() in SUBMIT_BUTTON_LABELS:
            return SUBMIT_BUTTON_LABELS[key.lower()]
        if key.startswith('btn_') or key.endswith('_submit'):
            label = key.replace('_', ' ').replace('btn ', '').strip()
            return label.title()
    for key, value in post.items():
        if key in SKIP_POST_KEYS:
            continue
        if isinstance(value, str) and value.lower() in SUBMIT_BUTTON_LABELS:
            return SUBMIT_BUTTON_LABELS[value.lower()]
    return ''


def _label_for_field(key: str) -> str:
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    cleaned = key.replace('_', ' ').strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else key


def _truncate(value: str, max_len: int = 80) -> str:
    value = ' '.join(str(value).split())
    if len(value) > max_len:
        return f'{value[:max_len]}…'
    return value


def _post_value(post, key: str) -> str:
    if key not in post:
        return ''
    value = post.get(key)
    if isinstance(value, list):
        value = value[0] if value else ''
    text = str(value).strip()
    if not text or text in {'***', 'on', 'off'}:
        if text == 'on':
            return 'Có'
        if text == 'off':
            return 'Không'
        return ''
    if key in {'is_active', 'is_employed', 'is_published'}:
        return 'Có' if text.lower() in {'1', 'true', 'on', 'yes'} else 'Không'
    return _truncate(text)


def describe_post_highlights(request: HttpRequest, url_name: str) -> str:
    post = getattr(request, 'POST', None)
    if not post:
        return ''

    keys = URL_POST_HIGHLIGHTS.get(url_name, [])
    if not keys:
        keys = [
            k for k in post.keys()
            if k not in SKIP_POST_KEYS and not k.startswith('csrf')
        ][:5]

    parts = []
    for key in keys:
        value = _post_value(post, key)
        if value:
            parts.append(f'{_label_for_field(key)}: {value}')

    button = _detect_submit_button(request)
    if button and not parts:
        return f'nút [{button}]'

    if button:
        return f'nút [{button}] · ' + ' · '.join(parts)
    if parts:
        return ' · '.join(parts)
    return ''


def describe_query_tab(request: HttpRequest) -> str:
    parts = []
    tab = request.GET.get('tab', '').strip()
    if tab:
        tab_labels = {
            'department': 'tab Phòng ban',
            'division': 'tab Bộ phận',
            'recruitment': 'tab Tuyển dụng',
            'training': 'tab Đào tạo',
            'assessment': 'tab Kiểm tra',
        }
        parts.append(tab_labels.get(tab, f'tab {tab}'))
    page = request.GET.get('page', '').strip()
    if page and page != '1':
        parts.append(f'trang {page}')
    q = request.GET.get('q', '').strip()
    if q:
        parts.append(f'tìm "{_truncate(q, 40)}"')
    return ' · '.join(parts)


def _path_namespace(path: str) -> str:
    for prefix, namespace in PATH_PREFIXES:
        if path.startswith(prefix):
            return namespace
    return ''


def _lookup_url_entry(
    entry: dict[str, str] | str | None,
    method: str,
) -> str:
    if isinstance(entry, dict):
        return entry.get(method) or entry.get('GET') or entry.get('POST') or ''
    return entry or ''


def _describe_equipment_url(url_name: str, method: str) -> str:
    """Sinh mô tả cho ~60 route thiết bị (IT / Sản xuất / chung)."""
    branch = ''
    base = url_name
    if base.endswith('_it'):
        branch = ' IT'
        base = base[:-3]
    elif base.endswith('_production'):
        branch = ' Sản xuất'
        base = base[:-12]

    if method == 'GET':
        verb_open = 'xem'
        verb_do = 'mở'
    elif method == 'POST':
        verb_open = 'gửi form'
        verb_do = 'thực hiện'
    else:
        verb_open = 'thao tác'
        verb_do = 'thao tác'

    patterns: dict[str, tuple[str, str]] = {
        'dashboard': (verb_open, f'dashboard thiết bị{branch}'),
        'device_list': (verb_open, f'danh sách thiết bị{branch}'),
        'device_add': (verb_do, f'form thêm thiết bị{branch}'),
        'it_repair_list': (verb_open, f'danh sách phiếu sửa chữa{branch}'),
        'it_repair_detail': (verb_open, f'chi tiết phiếu sửa chữa{branch}'),
        'import_export_hub': (verb_open, f'nhập/xuất thiết bị{branch}'),
        'category_list': (verb_open, f'danh mục loại thiết bị{branch}'),
        'category_add': (verb_do, f'form thêm loại thiết bị{branch}'),
        'category_edit': (verb_do, f'form sửa loại thiết bị{branch}'),
        'category_delete': ('xóa', f'loại thiết bị{branch}'),
        'export_devices': ('xuất', f'danh sách thiết bị{branch} ra Excel'),
        'download_sample': ('tải', f'file mẫu nhập thiết bị{branch}'),
        'import_devices': ('nhập', f'thiết bị{branch} từ Excel'),
        'delete_bulk_devices': ('xóa hàng loạt', f'thiết bị{branch}'),
        'device_detail_manage': (verb_open, 'chi tiết thiết bị'),
        'device_edit': (verb_do, 'form sửa thiết bị'),
        'device_history': (verb_open, 'lịch sử thiết bị'),
        'device_update_history': (verb_open, 'lịch sử cập nhật thiết bị'),
        'device_qr_public': (verb_open, 'mã QR thiết bị (công khai)'),
        'agent_guide': (verb_open, 'hướng dẫn cài agent thiết bị'),
        'agent_install_gate': (verb_open, 'trang yêu cầu cài agent'),
        'agent_download_installer': ('tải', 'trình cài JustPlay Agent'),
        'request_agent_rescan': ('yêu cầu', 'quét lại thiết bị qua agent'),
    }
    if base in patterns:
        v, rest = patterns[base]
        return f'{v} {rest}'
    if base.startswith('api_') or base.startswith('agent_'):
        return f'{verb_do} {base.replace("_", " ")}{branch}'
    readable = base.replace('_', ' ')
    return f'{verb_open} {readable}{branch}'


def resolve_url_description(request: HttpRequest, url_name: str) -> str:
    method = request.method.upper()
    path = request.path
    resolver = getattr(request, 'resolver_match', None)
    kwargs = dict(getattr(resolver, 'kwargs', None) or {})

    namespace = _path_namespace(path)
    if namespace == 'equipment' and url_name:
        base = _describe_equipment_url(url_name, method)
        extras = []
        if method == 'POST':
            post_hint = describe_post_highlights(request, url_name or '')
            if post_hint:
                extras.append(post_hint)
        if kwargs:
            id_part = ' · '.join(f'#{v}' for v in kwargs.values())
            if id_part:
                extras.append(id_part)
        if extras:
            return f'{base} ({", ".join(extras)})'
        return base

    if namespace and url_name:
        ns_entry = NAMESPACE_URL_DESCRIPTIONS.get(f'{namespace}:{url_name}')
        ns_base = _lookup_url_entry(ns_entry, method)
        if ns_base:
            ns_base = _format_template(ns_base, kwargs)
            extras = []
            if method == 'GET':
                query_hint = describe_query_tab(request)
                if query_hint:
                    extras.append(query_hint)
            elif method == 'POST':
                post_hint = describe_post_highlights(request, url_name or '')
                if post_hint:
                    extras.append(post_hint)
            if extras:
                return f'{ns_base} ({extras[0]})' if len(extras) == 1 else f'{ns_base} ({", ".join(extras)})'
            return ns_base

    # url_name trùng giữa app — phân biệt theo path
    if url_name == 'detail':
        if path.startswith('/reports/'):
            base = 'xem chi tiết báo cáo công việc #{pk}'
            return _format_template(base, kwargs)
        if path.startswith('/announcements/'):
            base = 'xem chi tiết thông báo #{pk}'
            return _format_template(base, kwargs)

    entry = URL_DESCRIPTIONS.get(url_name or '')
    base = _lookup_url_entry(entry, method)
    if not base:
        base = _fallback_from_path(request.path, method)

    if base:
        base = _format_template(base, kwargs)
    else:
        base = _fallback_from_path(request.path, method)

    extras = []
    if method == 'GET':
        query_hint = describe_query_tab(request)
        if query_hint:
            extras.append(query_hint)
    elif method == 'POST':
        post_hint = describe_post_highlights(request, url_name or '')
        if post_hint:
            extras.append(post_hint)

    if extras:
        return f'{base} ({extras[0]})' if len(extras) == 1 else f'{base} ({", ".join(extras)})'
    return base


def _fallback_from_path(path: str, method: str) -> str:
    path = path.rstrip('/') or '/'
    segments = [s for s in path.split('/') if s]

    if method == 'GET':
        verb = 'xem trang'
    elif method == 'POST':
        verb = 'gửi form'
    elif method == 'DELETE':
        verb = 'xóa'
    else:
        verb = 'thao tác'

    if not segments:
        return f'{verb} trang chủ'

    last = segments[-1]
    if last.isdigit():
        resource = segments[-2] if len(segments) >= 2 else 'mục'
        return f'{verb} {resource} #{last}'

    action_tokens = {
        'add': 'thêm mới',
        'create': 'tạo mới',
        'edit': 'chỉnh sửa',
        'delete': 'xóa',
        'remove': 'gỡ bỏ',
        'export': 'xuất dữ liệu',
        'import': 'nhập dữ liệu',
        'download': 'tải xuống',
        'upload': 'tải lên',
        'permissions': 'phân quyền',
        'reset-password': 'đặt lại mật khẩu',
        'toggle-employed': 'đổi trạng thái làm việc',
    }
    for seg in reversed(segments):
        if seg in action_tokens:
            target = segments[segments.index(seg) - 1] if segments.index(seg) > 0 else ''
            if target:
                return f'{action_tokens[seg]} {target.replace("-", " ")}'
            return action_tokens[seg]

    readable = last.replace('-', ' ').replace('_', ' ')
    return f'{verb} {readable}'


def build_detailed_summary(
    request: HttpRequest,
    action: str,
    module_label: str = '',
    object_repr: str = '',
) -> str:
    from hrm.permissions import get_profile

    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    profile = get_profile(user) if user else None
    if profile and profile.full_name:
        display = profile.full_name
    elif user:
        display = user.get_full_name() or user.username
    else:
        display = request.POST.get('username', 'Khách') if hasattr(request, 'POST') else 'Khách'

    resolver = getattr(request, 'resolver_match', None)
    url_name = getattr(resolver, 'url_name', '') or ''

    if action == UserActivityLog.ACTION_LOGIN:
        return f'{display} đăng nhập thành công vào portal'
    if action == UserActivityLog.ACTION_LOGOUT:
        return f'{display} bấm Đăng xuất khỏi hệ thống'
    if action == UserActivityLog.ACTION_LOGIN_FAILED:
        username = request.POST.get('username', 'Không rõ') if hasattr(request, 'POST') else 'Không rõ'
        return f'Đăng nhập thất bại — thử tài khoản [{username}]'

    detail = resolve_url_description(request, url_name)

    if object_repr and object_repr not in detail:
        detail = f'{detail} — {object_repr}'

    if not detail.strip():
        detail = _fallback_from_path(request.path, request.method.upper())

    if not detail.strip() and module_label:
        action_labels = dict(UserActivityLog.ACTION_CHOICES)
        verb = action_labels.get(action, action).lower()
        detail = f'{verb} trang {module_label}'

    prefix_map = {
        UserActivityLog.ACTION_VIEW: 'đã',
        UserActivityLog.ACTION_CREATE: 'đã',
        UserActivityLog.ACTION_UPDATE: 'đã',
        UserActivityLog.ACTION_DELETE: 'đã',
        UserActivityLog.ACTION_EXPORT: 'đã',
        UserActivityLog.ACTION_IMPORT: 'đã',
    }
    prefix = prefix_map.get(action, 'đã')

    if detail.startswith(('xem ', 'mở ', 'tải ', 'chuyển ')):
        return f'{display} {detail}'
    if detail.startswith(('tạo ', 'cập nhật ', 'xóa ', 'lưu ', 'nộp ', 'đăng ', 'nhập ', 'xuất ', 'đặt ', 'bật/', 'chuyển ', 'đánh dấu ', 'bấm ', 'gửi ', 'thêm ', 'sửa ', 'đổi ')):
        return f'{display} {detail}'

    return f'{display} {prefix} {detail}'
