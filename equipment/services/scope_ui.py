"""Nhãn & bộ lọc giao diện theo phạm vi Quản lý thiết bị IT / sản xuất."""

from __future__ import annotations

from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION
from equipment.services.device_categories import (
    categories_by_group,
    category_codes_for_profile,
)


def is_it_scope(scope: str | None) -> bool:
    return scope != SCOPE_PRODUCTION


def _filter_category_groups(groups, allowed: set[str]):
    result = []
    for group_code, group_label, items in groups:
        filtered = [(code, name) for code, name in items if code in allowed]
        if filtered:
            result.append((group_code, group_label, filtered))
    return result


def categories_by_group_for_scope(scope: str | None):
    """Chỉ loại thuộc profile it hoặc machine."""
    from equipment.categories import CATEGORY_CHOICES_BY_GROUP

    profile = 'it' if is_it_scope(scope) else 'machine'
    allowed = set(category_codes_for_profile(profile))
    if not allowed:
        return categories_by_group()

    filtered = _filter_category_groups(categories_by_group(), allowed)
    if filtered:
        return filtered

    # DB có loại active nhưng không khớp profile (thiếu/sai import_profile) — dùng seed tĩnh.
    return _filter_category_groups(CATEGORY_CHOICES_BY_GROUP, allowed)


def scope_ui_context(scope: str | None) -> dict:
    it = is_it_scope(scope)
    if it:
        return {
            'is_it_scope': True,
            'is_production_scope': False,
            'scope_icon': 'pc-display',
            'scope_page_intro': (
                'Máy tính, mạng, thiết bị văn phòng — Agent quét một lần khi cài, theo dõi hostname, IP, Windows.'
            ),
            'scope_list_search_placeholder': 'Mã TB, tên, serial, hostname, IP, người dùng…',
            'scope_list_col_specs': 'Hostname / IP',
            'scope_list_col_usage': 'Phòng ban / NSD',
            'scope_add_title': 'Thêm thiết bị IT',
            'scope_edit_title': 'Sửa thiết bị IT',
            'scope_category_intro': 'Loại dùng cho nhập Excel và lọc danh sách thiết bị IT (PC, mạng, in ấn…).',
            'scope_import_intro': 'Mỗi file Excel một loại thiết bị IT — cột hostname/IP nếu có trong mẫu.',
            'scope_dashboard_extra_label': 'Tổng giá trị tài sản',
            'scope_dashboard_issues_location': 'Phòng / vị trí',
        }
    return {
        'is_it_scope': False,
        'is_production_scope': True,
        'scope_icon': 'gear-wide-connected',
        'scope_page_intro': (
            'Máy may, thiết bị xưởng — theo dõi chuyền, bàn giao, số lượng và chi phí bảo trì.'
        ),
        'scope_list_search_placeholder': 'Mã TB, tên…',
        'scope_list_col_specs': 'Model / Serial',
        'scope_list_col_usage': 'Chuyền / phòng ban',
        'scope_add_title': 'Thêm thiết bị sản xuất',
        'scope_edit_title': 'Sửa thiết bị sản xuất',
        'scope_category_intro': 'Loại máy xưởng — dùng khi nhập Excel và lọc danh sách sản xuất.',
        'scope_import_intro': 'Mỗi file Excel một loại máy (may, cắt, ủi…) — ghi rõ chuyền và vị trí lắp.',
        'scope_dashboard_extra_label': 'Chi phí sửa (năm)',
        'scope_dashboard_issues_location': 'Chuyền / xưởng',
    }
