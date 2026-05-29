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


def resolve_url_description(request: HttpRequest, url_name: str) -> str:
    method = request.method.upper()
    path = request.path
    resolver = getattr(request, 'resolver_match', None)
    kwargs = dict(getattr(resolver, 'kwargs', None) or {})

    # url_name trùng giữa app — phân biệt theo path
    if url_name == 'detail':
        if path.startswith('/reports/'):
            base = 'xem chi tiết báo cáo công việc #{pk}'
            return _format_template(base, kwargs)
        if path.startswith('/announcements/'):
            base = 'xem chi tiết thông báo #{pk}'
            return _format_template(base, kwargs)

    entry = URL_DESCRIPTIONS.get(url_name or '')
    if isinstance(entry, dict):
        base = entry.get(method) or entry.get('GET') or entry.get('POST') or ''
    elif isinstance(entry, str):
        base = entry
    else:
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

    if not detail and module_label:
        action_labels = dict(UserActivityLog.ACTION_CHOICES)
        verb = action_labels.get(action, action).lower()
        detail = f'{verb} {module_label}'

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
