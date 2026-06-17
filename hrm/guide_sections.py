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

# Nhóm mục lục — đánh số lại trong từng nhóm (không nhảy số khi mục bị ẩn theo quyền).
TOC_GROUP_LABELS: dict[str, str] = {
    'foundation': 'Nền tảng',
    'access': 'Quyền & thông báo',
    'daily': 'Công việc hàng ngày',
    'tools': 'Công cụ & module',
    'special': 'Chuyên biệt',
    'admin': 'HR / Quản trị',
    'help': 'Hỗ trợ',
}

# modules=None → luôn hiển thị (phần nền tảng)
# preview: (ảnh static/images/guide/, nhãn) — dùng ở mục «Bắt đầu nhanh»
# toc_label: tên hiển thị (không kèm số) — dùng khi build toc_display theo nhóm
GUIDE_SECTIONS: list[dict] = [
    {
        'id': 'bat-dau',
        'toc': '0. Bắt đầu nhanh',
        'toc_short': '0. Bắt đầu',
        'toc_label': 'Bắt đầu nhanh',
        'toc_group': 'foundation',
        'modules': None,
        'order': 0,
        'preview': ('02-trang-chu.png', 'Trang chủ'),
    },
    {
        'id': 'gioi-thieu',
        'toc': '1. Giới thiệu',
        'toc_short': '1. GT',
        'toc_label': 'Giới thiệu',
        'toc_group': 'foundation',
        'modules': None,
        'order': 10,
    },
    {
        'id': 'chuan-bi',
        'toc': '2. Chuẩn bị',
        'toc_short': '2. CB',
        'toc_label': 'Chuẩn bị',
        'toc_group': 'foundation',
        'modules': None,
        'order': 20,
    },
    {
        'id': 'dang-nhap',
        'toc': '3. Đăng nhập',
        'toc_short': '3. ĐN',
        'toc_label': 'Đăng nhập',
        'toc_group': 'foundation',
        'modules': None,
        'order': 30,
        'preview': ('01-dang-nhap.png', 'Đăng nhập'),
    },
    {
        'id': 'doi-mat-khau',
        'toc': '4. Đổi mật khẩu',
        'toc_short': '4. MK',
        'toc_label': 'Đổi mật khẩu',
        'toc_group': 'foundation',
        'modules': None,
        'order': 40,
    },
    {
        'id': 'phan-quyen',
        'toc': 'Phân quyền menu',
        'toc_short': 'PQ',
        'toc_label': 'Phân quyền menu',
        'toc_group': 'access',
        'modules': [MODULE_PERMISSIONS],
        'order': 60,
        'preview': ('11-phan-quyen.png', 'Phân quyền'),
        'admin_only': True,
    },
    {
        'id': 'thong-bao',
        'toc': 'Thông báo',
        'toc_short': 'TB',
        'toc_label': 'Thông báo',
        'toc_group': 'access',
        'modules': [MODULE_ANNOUNCEMENTS],
        'order': 70,
        'preview': ('05-thong-bao.png', 'Thông báo'),
    },
    {
        'id': 'bao-cao',
        'toc': 'Báo cáo công việc',
        'toc_short': 'BC',
        'toc_label': 'Báo cáo công việc',
        'toc_group': 'daily',
        'modules': [MODULE_REPORTS],
        'order': 80,
        'preview': ('06-bao-cao.png', 'Báo cáo'),
    },
    {
        'id': 'kpi',
        'toc': 'KPI',
        'toc_short': 'KPI',
        'toc_label': 'KPI',
        'toc_group': 'daily',
        'modules': [MODULE_KPI],
        'order': 90,
        'preview': ('09-kpi.png', 'KPI'),
    },
    {
        'id': 'dao-tao',
        'toc': 'Đào tạo',
        'toc_short': 'Học',
        'toc_label': 'Đào tạo',
        'toc_group': 'daily',
        'modules': [MODULE_TRAINING],
        'order': 100,
        'preview': ('07-dao-tao.png', 'Học'),
    },
    {
        'id': 'kiem-tra',
        'toc': 'Kiểm tra',
        'toc_short': 'Thi',
        'toc_label': 'Kiểm tra',
        'toc_group': 'daily',
        'modules': [MODULE_ASSESSMENT],
        'order': 110,
        'preview': ('08-kiem-tra.png', 'Thi'),
    },
    {
        'id': 'tai-lieu',
        'toc': 'Tài liệu & Hỏi đáp',
        'toc_short': 'TL',
        'toc_label': 'Tài liệu & Hỏi đáp',
        'toc_group': 'tools',
        'modules': [MODULE_DOCUMENTS],
        'order': 115,
        'preview': ('12-tai-lieu.png', 'Tài liệu'),
    },
    {
        'id': 'cong-viec',
        'toc': 'Công việc',
        'toc_short': 'CV',
        'toc_label': 'Công việc',
        'toc_group': 'tools',
        'modules': [MODULE_TASKS],
        'order': 120,
        'preview': ('13-cong-viec.png', 'Công việc'),
    },
    {
        'id': 'de-xuat',
        'toc': 'Đề xuất mới',
        'toc_short': 'ĐX',
        'toc_label': 'Đề xuất mới',
        'toc_group': 'tools',
        'modules': [MODULE_DE_XUAT],
        'order': 130,
        'preview': ('14-de-xuat.png', 'Đề xuất'),
    },
    {
        'id': 'ho-tro',
        'toc': 'Hỗ trợ kỹ thuật',
        'toc_short': 'HT',
        'toc_label': 'Hỗ trợ kỹ thuật',
        'toc_group': 'tools',
        'modules': [MODULE_HO_TRO],
        'order': 140,
        'preview': ('15-ho-tro.png', 'Hỗ trợ'),
    },
    {
        'id': 'thiet-bi',
        'toc': 'Quản lý thiết bị',
        'toc_short': 'TB',
        'toc_label': 'Quản lý thiết bị',
        'toc_group': 'tools',
        'modules': [MODULE_EQUIPMENT],
        'order': 150,
        'preview': ('16-thiet-bi.png', 'Thiết bị'),
    },
    {
        'id': 'gop-y',
        'toc': 'Góp ý',
        'toc_short': 'GY',
        'toc_label': 'Góp ý',
        'toc_group': 'tools',
        'modules': [MODULE_FEEDBACK],
        'order': 160,
        'preview': ('17-gop-y.png', 'Góp ý'),
    },
    {
        'id': 'kho-npl',
        'toc': 'Kho NPL',
        'toc_short': 'KN',
        'toc_label': 'Kho NPL',
        'toc_group': 'special',
        'modules': [MODULE_KHO_NPL],
        'order': 170,
        'preview': ('18-kho-npl.png', 'Kho NPL'),
    },
    {
        'id': 'kiotviet',
        'toc': 'KiotViet',
        'toc_short': 'KV',
        'toc_label': 'KiotViet',
        'toc_group': 'special',
        'modules': [MODULE_KIOTVIET],
        'order': 175,
        'preview': ('19-kiotviet.png', 'KiotViet'),
    },
    {
        'id': 'nas',
        'toc': 'Thư mục NAS',
        'toc_short': 'NAS',
        'toc_label': 'Thư mục NAS',
        'toc_group': 'special',
        'modules': [MODULE_NAS_STORAGE],
        'order': 180,
        'preview': ('20-nas.png', 'NAS'),
    },
    {
        'id': 'tuyen-dung',
        'toc': 'Tuyển dụng',
        'toc_short': 'TD',
        'toc_label': 'Tuyển dụng',
        'toc_group': 'admin',
        'modules': [MODULE_RECRUITMENT],
        'order': 190,
        'preview': ('21-tuyen-dung.png', 'Tuyển dụng'),
        'admin_only': True,
    },
    {
        'id': 'quan-tri',
        'toc': 'Quản trị nhân sự',
        'toc_short': 'NS',
        'toc_label': 'Quản trị nhân sự',
        'toc_group': 'admin',
        'modules': [MODULE_HRM],
        'order': 200,
        'preview': ('10-nhan-su.png', 'Nhân sự'),
        'admin_only': True,
    },
    {
        'id': 'quan-tri-he-thong',
        'toc': 'Quản trị hệ thống',
        'toc_short': 'Audit',
        'toc_label': 'Quản trị hệ thống',
        'toc_group': 'admin',
        'modules': [MODULE_AUDIT],
        'order': 210,
        'preview': ('22-audit.png', 'Audit'),
        'admin_only': True,
    },
    {
        'id': 'faq',
        'toc': 'Câu hỏi thường gặp',
        'toc_short': 'FAQ',
        'toc_label': 'Câu hỏi thường gặp',
        'toc_group': 'help',
        'modules': None,
        'order': 999,
    },
]


def get_section_by_id(section_id: str) -> dict | None:
    for sec in GUIDE_SECTIONS:
        if sec['id'] == section_id:
            return sec
    return None


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


def build_guide_toc_groups(visible_sections: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Gán tiêu đề hiển thị và gom mục theo nhóm cho sidebar.
    - toc_display: đánh số liên tục toàn trang (accordion) — 0–4 nền tảng, rồi 5, 6, 7…
    - toc_sidebar_display: đánh số lại trong từng nhóm (sidebar)
    """
    enriched: list[dict] = []
    group_counters: dict[str, int] = {}
    global_n = -1
    toc_groups: list[dict] = []

    for sec in visible_sections:
        item = dict(sec)
        group = item.get('toc_group') or 'tools'
        label = item.get('toc_label') or item['toc']
        short = item.get('toc_short') or label

        if group == 'foundation':
            item['toc_display'] = item['toc']
            item['toc_short_display'] = item.get('toc_short') or item['toc']
            global_n = max(global_n, int(item['toc'].split('.')[0]))
        elif group == 'help':
            item['toc_display'] = label
            item['toc_short_display'] = short
        else:
            global_n += 1
            item['toc_display'] = f'{global_n}. {label}'
            item['toc_short_display'] = f'{global_n}. {short}'

        if group == 'foundation':
            item['toc_sidebar_display'] = item['toc']
            item['toc_short_sidebar'] = item.get('toc_short') or item['toc']
        elif group == 'help':
            item['toc_sidebar_display'] = label
            item['toc_short_sidebar'] = short
        else:
            group_counters[group] = group_counters.get(group, 0) + 1
            n = group_counters[group]
            item['toc_sidebar_display'] = f'{n}. {label}'
            item['toc_short_sidebar'] = f'{n}. {short}'

        enriched.append(item)
        if not toc_groups or toc_groups[-1]['id'] != group:
            toc_groups.append({
                'id': group,
                'label': TOC_GROUP_LABELS.get(group, group),
                'sections': [],
            })
        toc_groups[-1]['sections'].append(item)

    return enriched, toc_groups


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
