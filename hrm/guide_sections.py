"""
Registry mục hướng dẫn — khớp quyền xem module (nhóm quyền / phòng ban).
"""

from hrm.module_permissions import (
    MODULE_ANNOUNCEMENTS,
    MODULE_ASSESSMENT,
    MODULE_AUDIT,
    MODULE_DE_XUAT,
    MODULE_DOCUMENTS,
    MODULE_EQUIPMENT,
    MODULE_FEEDBACK,
    MODULE_HO_TRO,
    MODULE_HRM,
    MODULE_KIOTVIET,
    MODULE_KHO_NPL,
    MODULE_KPI,
    MODULE_NAS_STORAGE,
    MODULE_PERMISSIONS,
    MODULE_RECRUITMENT,
    MODULE_REPORTS,
    MODULE_TASKS,
    MODULE_TRAINING,
    is_portal_module_visible,
    user_can_access_module,
)

# modules=None → luôn hiển thị (phần nền tảng)
# preview: (ảnh static/images/guide/, nhãn) — dùng ở mục «Bắt đầu nhanh»
GUIDE_SECTIONS: list[dict] = [
    {
        'id': 'bat-dau',
        'toc': '0. Bắt đầu nhanh',
        'toc_short': '0. Bắt đầu',
        'modules': None,
        'order': 0,
        'preview': ('02-trang-chu.png', 'Trang chủ'),
    },
    {
        'id': 'gioi-thieu',
        'toc': '1. Giới thiệu',
        'toc_short': '1. GT',
        'modules': None,
        'order': 10,
    },
    {
        'id': 'chuan-bi',
        'toc': '2. Chuẩn bị',
        'toc_short': '2. CB',
        'modules': None,
        'order': 20,
    },
    {
        'id': 'dang-nhap',
        'toc': '3. Đăng nhập',
        'toc_short': '3. ĐN',
        'modules': None,
        'order': 30,
        'preview': ('01-dang-nhap.png', 'Đăng nhập'),
    },
    {
        'id': 'doi-mat-khau',
        'toc': '4. Đổi mật khẩu',
        'toc_short': '4. MK',
        'modules': None,
        'order': 40,
    },
    {
        'id': 'phan-quyen',
        'toc': '6. Phân quyền menu',
        'toc_short': '6. PQ',
        'modules': [MODULE_PERMISSIONS],
        'order': 60,
        'preview': ('11-phan-quyen.png', 'Phân quyền'),
        'admin_only': True,
    },
    {
        'id': 'thong-bao',
        'toc': '7. Thông báo',
        'toc_short': '7. TB',
        'modules': [MODULE_ANNOUNCEMENTS],
        'order': 70,
        'preview': ('05-thong-bao.png', 'Thông báo'),
    },
    {
        'id': 'bao-cao',
        'toc': '8. Báo cáo công việc',
        'toc_short': '8. BC',
        'modules': [MODULE_REPORTS],
        'order': 80,
        'preview': ('06-bao-cao.png', 'Báo cáo'),
    },
    {
        'id': 'kpi',
        'toc': '9. KPI',
        'toc_short': '9. KPI',
        'modules': [MODULE_KPI],
        'order': 90,
        'preview': ('09-kpi.png', 'KPI'),
    },
    {
        'id': 'dao-tao',
        'toc': '10. Đào tạo',
        'toc_short': '10. Học',
        'modules': [MODULE_TRAINING],
        'order': 100,
        'preview': ('07-dao-tao.png', 'Học'),
    },
    {
        'id': 'kiem-tra',
        'toc': '11. Kiểm tra',
        'toc_short': '11. Thi',
        'modules': [MODULE_ASSESSMENT],
        'order': 110,
        'preview': ('08-kiem-tra.png', 'Thi'),
    },
    {
        'id': 'tai-lieu',
        'toc': 'Tài liệu & Hỏi đáp',
        'toc_short': 'TL',
        'modules': [MODULE_DOCUMENTS],
        'order': 115,
        'preview': ('12-tai-lieu.png', 'Tài liệu'),
    },
    {
        'id': 'cong-viec',
        'toc': 'Công việc',
        'toc_short': 'CV',
        'modules': [MODULE_TASKS],
        'order': 120,
        'preview': ('13-cong-viec.png', 'Công việc'),
    },
    {
        'id': 'de-xuat',
        'toc': 'Đề xuất mới',
        'toc_short': 'ĐX',
        'modules': [MODULE_DE_XUAT],
        'order': 130,
        'preview': ('14-de-xuat.png', 'Đề xuất'),
    },
    {
        'id': 'ho-tro',
        'toc': 'Hỗ trợ kỹ thuật',
        'toc_short': 'HT',
        'modules': [MODULE_HO_TRO],
        'order': 140,
        'preview': ('15-ho-tro.png', 'Hỗ trợ'),
    },
    {
        'id': 'thiet-bi',
        'toc': 'Quản lý thiết bị',
        'toc_short': 'TB',
        'modules': [MODULE_EQUIPMENT],
        'order': 150,
        'preview': ('16-thiet-bi.png', 'Thiết bị'),
    },
    {
        'id': 'gop-y',
        'toc': 'Góp ý',
        'toc_short': 'GY',
        'modules': [MODULE_FEEDBACK],
        'order': 160,
        'preview': ('17-gop-y.png', 'Góp ý'),
    },
    {
        'id': 'kho-npl',
        'toc': 'Kho NPL',
        'toc_short': 'KN',
        'modules': [MODULE_KHO_NPL],
        'order': 170,
        'preview': ('18-kho-npl.png', 'Kho NPL'),
    },
    {
        'id': 'kiotviet',
        'toc': 'KiotViet',
        'toc_short': 'KV',
        'modules': [MODULE_KIOTVIET],
        'order': 175,
        'preview': ('19-kiotviet.png', 'KiotViet'),
    },
    {
        'id': 'nas',
        'toc': 'Thư mục NAS',
        'toc_short': 'NAS',
        'modules': [MODULE_NAS_STORAGE],
        'order': 180,
        'preview': ('20-nas.png', 'NAS'),
    },
    {
        'id': 'tuyen-dung',
        'toc': 'Tuyển dụng',
        'toc_short': 'TD',
        'modules': [MODULE_RECRUITMENT],
        'order': 190,
        'preview': ('21-tuyen-dung.png', 'Tuyển dụng'),
        'admin_only': True,
    },
    {
        'id': 'quan-tri',
        'toc': 'Quản trị nhân sự',
        'toc_short': 'NS',
        'modules': [MODULE_HRM],
        'order': 200,
        'preview': ('10-nhan-su.png', 'Nhân sự'),
        'admin_only': True,
    },
    {
        'id': 'quan-tri-he-thong',
        'toc': 'Quản trị hệ thống',
        'toc_short': 'HT',
        'modules': [MODULE_AUDIT],
        'order': 210,
        'preview': ('22-audit.png', 'Audit'),
        'admin_only': True,
    },
    {
        'id': 'faq',
        'toc': 'Câu hỏi thường gặp',
        'toc_short': 'FAQ',
        'modules': None,
        'order': 999,
    },
]


def user_can_manage_module_in_guide(user, module_key: str) -> bool:
    """Có quyền thêm/sửa/xóa module — hiện phần «Dành cho HR / Quản trị»."""
    from hrm.module_permissions import (
        user_can_create_module,
        user_can_delete_module,
        user_can_update_module,
    )

    if not is_portal_module_visible(module_key):
        return False
    return (
        user_can_create_module(user, module_key)
        or user_can_update_module(user, module_key)
        or user_can_delete_module(user, module_key)
    )


def _section_has_module_manage(user, section: dict) -> bool:
    modules = section.get('modules') or []
    return any(user_can_manage_module_in_guide(user, mod) for mod in modules)


def section_visible_for_user(user, section: dict) -> bool:
    modules = section.get('modules')
    if not modules:
        return True
    visible_mods = [
        mod for mod in modules
        if is_portal_module_visible(mod) and user_can_access_module(user, mod)
    ]
    if not visible_mods:
        return False
    if section.get('admin_only'):
        return any(user_can_manage_module_in_guide(user, mod) for mod in visible_mods)
    return True


def get_guide_admin_section_ids(user) -> set[str]:
    """Section ID được xem thêm nội dung HR / Quản trị (thêm/sửa/xóa)."""
    ids: set[str] = set()
    for sec in GUIDE_SECTIONS:
        if sec.get('modules') and _section_has_module_manage(user, sec):
            ids.add(sec['id'])
    return ids


def get_visible_guide_sections(user) -> list[dict]:
    return [
        sec for sec in sorted(GUIDE_SECTIONS, key=lambda s: s['order'])
        if section_visible_for_user(user, sec)
    ]


def get_guide_preview_items(user) -> list[dict]:
    """Ảnh xem trước ở mục Bắt đầu nhanh — chỉ module user được xem."""
    items = []
    for sec in get_visible_guide_sections(user):
        preview = sec.get('preview')
        if not preview:
            continue
        img, label = preview
        items.append({
            'href': f"#{sec['id']}",
            'image': img,
            'label': label,
        })
    return items
