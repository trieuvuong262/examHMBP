from hrm.permissions import get_direct_manager_users


ATTENDANCE_DEMO_USERNAME = 'vuong-admin'
MODULE_CHAM_CONG = 'cham_cong'
MENU_PUNCH = 'punch'
MENU_SCHEDULE = 'schedule'
MENU_SUPPLEMENTS = 'supplements'
MENU_SITES = 'sites'
MENU_HR_REPORTS = 'hr_reports'


def attendance_demo_user(user) -> bool:
    """Demo chấm công chỉ mở cho một tài khoản."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return (getattr(user, 'username', '') or '').lower() == ATTENDANCE_DEMO_USERNAME


def can_punch(user) -> bool:
    from hrm.menu_permissions import user_can_access_menu

    return bool(getattr(user, 'is_authenticated', False) and user_can_access_menu(
        user, MODULE_CHAM_CONG, MENU_PUNCH,
    ))


def can_configure(user) -> bool:
    """Chỉ vuong-admin xem toàn công ty và cấu hình ca, địa điểm, báo cáo."""
    return attendance_demo_user(user)


def can_view_company(user) -> bool:
    return can_configure(user)


def can_view_payslip(actor, employee) -> bool:
    if not getattr(actor, 'is_authenticated', False):
        return False
    if actor.pk == getattr(employee, 'pk', None):
        return True
    if can_configure(actor):
        return True
    return any(manager.pk == actor.pk for manager in get_direct_manager_users(employee))


def can_approve_pay_adjustment(actor, item) -> bool:
    if not can_decide_for(actor, item.user):
        return False
    if item.created_by_id == actor.pk and not can_configure(actor):
        return False
    return True


def can_decide_for(actor, employee) -> bool:
    if not getattr(actor, 'is_authenticated', False):
        return False
    if actor.pk == getattr(employee, 'pk', None):
        return False
    if can_configure(actor):
        return True
    return any(manager.pk == actor.pk for manager in get_direct_manager_users(employee))


def member_path_allowed(user, path: str) -> bool:
    """Nhân sự vẫn vào cấu hình ca/địa điểm khi nhóm quyền chưa tách menu."""
    if not can_configure(user):
        return False
    return (
        path.startswith('/cham-cong/ca')
        or path.startswith('/cham-cong/dia-diem')
        or path.startswith('/cham-cong/cau-hinh')
        or path.startswith('/cham-cong/bao-cao')
        or path.startswith('/cham-cong/nhat-ky')
    )
