from django.db.utils import OperationalError, ProgrammingError


def attendance_nav(request):
    empty = {
        'jp_attendance_block': False,
        'jp_cc_pending_count': 0,
        'jp_cc_adjust_count': 0,
        'jp_cc_leave_count': 0,
        'jp_cc_bonus_count': 0,
        'jp_can_configure_attendance': False,
    }
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return empty
    try:
        from cham_cong.permissions import can_configure, can_punch
        from cham_cong.services import pending_badge_counts, should_force_punch

        configure = can_configure(user)
        if not configure and not can_punch(user):
            return empty
        pending, adjustments, leaves, bonuses = pending_badge_counts(user)
        return {
            'jp_attendance_block': should_force_punch(user),
            'jp_cc_pending_count': pending,
            'jp_cc_adjust_count': adjustments,
            'jp_cc_leave_count': leaves,
            'jp_cc_bonus_count': bonuses,
            'jp_can_configure_attendance': configure,
        }
    except (OperationalError, ProgrammingError):
        return empty
