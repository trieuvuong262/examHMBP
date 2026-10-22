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
        from cham_cong.models import AttendanceAdjustment, AttendanceSupplement, LeaveRequest, PayAdjustment
        from cham_cong.permissions import can_configure, can_view_company
        from cham_cong.services import should_force_punch, team_user_ids

        if can_view_company(user):
            pending = AttendanceSupplement.objects.filter(status=AttendanceSupplement.STATUS_PENDING).count()
            adjustments = AttendanceAdjustment.objects.filter(status=AttendanceAdjustment.STATUS_PENDING).count()
            leaves = LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).count()
            bonuses = PayAdjustment.objects.filter(status=PayAdjustment.STATUS_PENDING).count()
        else:
            ids = team_user_ids(user)
            pending = (
                AttendanceSupplement.objects.filter(
                    status=AttendanceSupplement.STATUS_PENDING, user_id__in=ids,
                ).count()
                if ids else 0
            )
            adjustments = (
                AttendanceAdjustment.objects.filter(
                    status=AttendanceAdjustment.STATUS_PENDING, user_id__in=ids,
                ).count()
                if ids else 0
            )
            leaves = (
                LeaveRequest.objects.filter(
                    status=LeaveRequest.STATUS_PENDING, user_id__in=ids,
                ).count()
                if ids else 0
            )
            bonuses = (
                PayAdjustment.objects.filter(
                    status=PayAdjustment.STATUS_PENDING, user_id__in=ids,
                ).count()
                if ids else 0
            )
        return {
            'jp_attendance_block': should_force_punch(user),
            'jp_cc_pending_count': pending,
            'jp_cc_adjust_count': adjustments,
            'jp_cc_leave_count': leaves,
            'jp_cc_bonus_count': bonuses,
            'jp_can_configure_attendance': can_configure(user),
        }
    except (OperationalError, ProgrammingError):
        return empty
