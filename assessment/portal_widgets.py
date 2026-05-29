"""Tóm tắt việc cần làm — hiển thị trên trang chủ portal."""

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from announcements.models import Announcement, AnnouncementRead
from hrm.permissions import (
    can_assign_tasks,
    can_submit_daily_report,
    can_view_team_reports,
    get_profile,
    get_report_team_users,
    is_gm,
    is_hod,
)
from hrm.module_permissions import MODULE_TASKS, user_can_access_module
from kpi.models import KpiPeriod, YearlyKpi
from reports.models import DailyWorkReport
from tasks.models import WorkTask

_PERIOD_STATUS_FIELD = {
    'Q1': 'q1_status',
    'Q2': 'q2_status',
    'Q3': 'q3_status',
    'Q4': 'q4_status',
    'H1': 'h1_status',
    'H2': 'h2_status',
    'Y': 'y_status',
}


def _period_label(period_type: str) -> str:
    return dict(KpiPeriod.PERIOD_CHOICES).get(period_type, period_type)


def _kpi_action_reminders(kpi_board, open_periods, role: str):
    """role: 'self' | 'manager' | 'gm'"""
    status_by_role = {
        'self': 'self_evaluating',
        'manager': 'manager_evaluating',
        'gm': 'general_evaluating',
    }
    target_status = status_by_role.get(role)
    if not target_status:
        return []

    items = []
    for period in open_periods:
        if period.year != kpi_board.year:
            continue
        field = _PERIOD_STATUS_FIELD.get(period.period_type)
        if not field:
            continue
        if getattr(kpi_board, field, None) != target_status:
            continue

        label = _period_label(period.period_type)
        if role == 'self':
            text = f'Kỳ {label} đang mở — chưa hoàn tất tự đánh giá KPI năm {kpi_board.year}.'
            action = 'Chấm KPI'
        elif role == 'manager':
            emp_profile = get_profile(kpi_board.employee)
            name = emp_profile.full_name if emp_profile and emp_profile.full_name else kpi_board.employee.username
            text = f'{name}: kỳ {label} đang chờ HOD chấm điểm.'
            action = 'Chấm điểm'
        else:
            emp_profile = get_profile(kpi_board.employee)
            name = emp_profile.full_name if emp_profile and emp_profile.full_name else kpi_board.employee.username
            text = f'{name}: kỳ {label} đang chờ GM chốt điểm.'
            action = 'Chốt KPI'

        items.append({
            'level': 'warning' if role == 'self' else 'info',
            'icon': 'bi-graph-up-arrow',
            'title': f'KPI {label} · năm {kpi_board.year}',
            'text': text,
            'url': reverse('kpi_detail', args=[kpi_board.id]),
            'action': action,
        })
    return items


def get_portal_dashboard(user):
    """Trả về danh sách widget nhắc việc (dict) cho trang chủ."""
    widgets = []
    today = timezone.localdate()
    profile = get_profile(user)

    # --- Thông báo chưa đọc ---
    active_ids = Announcement.objects.filter(is_active=True).values_list('id', flat=True)
    read_ids = AnnouncementRead.objects.filter(
        user=user,
        announcement_id__in=active_ids,
    ).values_list('announcement_id', flat=True)
    unread_count = len(set(active_ids) - set(read_ids))
    if unread_count:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-megaphone-fill',
            'title': 'Thông báo',
            'text': f'Còn {unread_count} thông báo chưa xác nhận đọc.',
            'url': reverse('announcements:list'),
            'action': 'Đọc ngay',
            'badge': unread_count,
        })

    # --- Báo cáo hôm nay (cá nhân — không áp dụng Giám đốc) ---
    if can_submit_daily_report(user):
        today_report = DailyWorkReport.objects.filter(
            employee=user,
            report_date=today,
        ).first()
        if not today_report or today_report.status != DailyWorkReport.STATUS_SUBMITTED:
            if today_report and today_report.status == DailyWorkReport.STATUS_DRAFT:
                text = f'Báo cáo ngày {today.strftime("%d/%m/%Y")} đang lưu nháp — nộp cho cấp trên trước tan ca.'
            else:
                text = f'Chưa nộp báo cáo công việc hôm nay ({today.strftime("%d/%m/%Y")}).'
            widgets.append({
                'level': 'danger',
                'icon': 'bi-clipboard-check-fill',
                'title': 'Báo cáo hàng ngày',
                'text': text,
                'url': reverse('reports:today'),
                'action': 'Nhập báo cáo',
            })

    # --- Công việc: việc chờ xác nhận / chờ duyệt ---
    if user_can_access_module(user, MODULE_TASKS):
        if can_assign_tasks(user):
            pending_review = WorkTask.objects.filter(
                assigner=user,
                project__isnull=True,
                status=WorkTask.STATUS_PENDING_REVIEW,
            ).count()
            rejected = WorkTask.objects.filter(
                assigner=user,
                project__isnull=True,
                status=WorkTask.STATUS_REJECTED,
            ).count()
            if pending_review:
                widgets.append({
                    'level': 'info',
                    'icon': 'bi-list-check',
                    'title': 'Công việc chờ duyệt',
                    'text': f'{pending_review} việc đã nộp — cần duyệt hoặc yêu cầu sửa.',
                    'url': reverse('tasks:assigned') + '?status=pending_review',
                    'action': 'Duyệt việc',
                    'badge': pending_review,
                })
            if rejected:
                widgets.append({
                    'level': 'warning',
                    'icon': 'bi-arrow-repeat',
                    'title': 'Việc bị từ chối',
                    'text': f'{rejected} việc bị từ chối — có thể giao lại cho người khác.',
                    'url': reverse('tasks:assigned') + '?status=rejected',
                    'action': 'Giao lại',
                    'badge': rejected,
                })

        pending_ack = WorkTask.objects.filter(
            assignee=user,
            project__isnull=True,
            status=WorkTask.STATUS_PENDING_ACK,
        ).count()
        if pending_ack:
            widgets.append({
                'level': 'warning',
                'icon': 'bi-bell-fill',
                'title': 'Việc chờ xác nhận',
                'text': f'Có {pending_ack} công việc mới cần bạn xác nhận hoặc từ chối.',
                'url': reverse('tasks:my') + '?status=pending_ack',
                'action': 'Xem việc',
                'badge': pending_ack,
            })

        revision_count = WorkTask.objects.filter(
            assignee=user,
            project__isnull=True,
            status=WorkTask.STATUS_REVISION,
        ).count()
        if revision_count:
            widgets.append({
                'level': 'danger',
                'icon': 'bi-pencil-square',
                'title': 'Việc cần sửa',
                'text': f'{revision_count} công việc cần bạn sửa và nộp lại.',
                'url': reverse('tasks:my') + '?status=revision',
                'action': 'Sửa việc',
                'badge': revision_count,
            })

    # --- KPI cá nhân ---
    open_periods = list(KpiPeriod.objects.filter(is_active=True))
    for kpi in YearlyKpi.objects.filter(employee=user).order_by('-year'):
        widgets.extend(_kpi_action_reminders(kpi, open_periods, 'self'))

    # --- HOD / GM: team chưa nộp BC ---
    if can_view_team_reports(user):
        team_users = get_report_team_users(user)
        if team_users.exists():
            submitted_ids = DailyWorkReport.objects.filter(
                report_date=today,
                status=DailyWorkReport.STATUS_SUBMITTED,
                employee__in=team_users,
            ).values_list('employee_id', flat=True)
            missing = team_users.exclude(pk__in=submitted_ids).count()
            if missing:
                widgets.append({
                    'level': 'info',
                    'icon': 'bi-people-fill',
                    'title': 'Báo cáo team',
                    'text': f'{missing} nhân viên chưa nộp báo cáo hôm nay ({today.strftime("%d/%m")}).',
                    'url': reverse('reports:team'),
                    'action': 'Xem team',
                    'badge': missing,
                })

    # --- HOD / GM: KPI cấp dưới ---
    team_kpis = YearlyKpi.objects.none()
    if is_gm(user):
        team_kpis = YearlyKpi.objects.exclude(employee=user).order_by('-year')
    elif is_hod(user) and profile:
        subs = profile.subordinates.all()
        team_kpis = YearlyKpi.objects.filter(
            Q(employee__in=subs) | Q(direct_manager=user),
        ).exclude(employee=user).distinct().order_by('-year')

    manager_role = 'gm' if is_gm(user) else 'manager'
    for kpi in team_kpis[:20]:
        widgets.extend(_kpi_action_reminders(kpi, open_periods, manager_role))

    # --- Bài thi đang mở (chưa làm) ---
    try:
        from assessment.models import Exam, ExamSubmission
        now = timezone.now()
        pending_exams = Exam.objects.filter(
            assigned_users=user,
            is_active=True,
            start_time__lte=now,
            end_time__gte=now,
        ).exclude(
            id__in=ExamSubmission.objects.filter(
                user=user,
                submitted_at__isnull=False,
            ).values_list('exam_id', flat=True),
        ).distinct()
        count = pending_exams.count()
        if count:
            widgets.append({
                'level': 'warning',
                'icon': 'bi-journal-check',
                'title': 'Bài kiểm tra',
                'text': f'Còn {count} bài thi đang mở — hoàn thành trước hạn chót.',
                'url': reverse('exam_list'),
                'action': 'Vào thi',
                'badge': count,
            })
    except Exception:
        pass

    return widgets
