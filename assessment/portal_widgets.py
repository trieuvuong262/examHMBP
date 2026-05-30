"""Tóm tắt việc cần làm — hiển thị trên trang chủ portal."""

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from announcements.models import Announcement, AnnouncementRead
from hrm.permissions import (
    can_assign_tasks,
    can_receive_assigned_tasks,
    can_submit_daily_report,
    can_view_team_reports,
    get_report_team_users,
)
from hrm.module_permissions import (
    MODULE_ASSESSMENT,
    MODULE_SERVICE_REQUESTS,
    MODULE_TASKS,
    MODULE_TRAINING,
    user_can_access_module,
)
from reports.models import DailyWorkReport
from tasks.models import WorkTask, WorkTaskHandoff


def _open_assignee_tasks(user):
    return WorkTask.objects.filter(
        assignee=user,
        status__in=WorkTask.OPEN_ASSIGNEE_STATUSES,
    )


def _assigner_pending_review_qs(user):
    return WorkTask.objects.filter(
        Q(assigner=user, project__isnull=True)
        | Q(project__owner=user, project__isnull=False),
        status=WorkTask.STATUS_PENDING_REVIEW,
    ).distinct()


def _assigner_rejected_qs(user):
    return WorkTask.objects.filter(
        Q(assigner=user, project__isnull=True)
        | Q(project__owner=user, project__isnull=False),
        status=WorkTask.STATUS_REJECTED,
    ).distinct()


def _task_widgets(user):
    """Widget công việc — nhắc đến khi hoàn thành."""
    if not user_can_access_module(user, MODULE_TASKS):
        return []

    widgets = []

    if can_receive_assigned_tasks(user):
        personal_open = _open_assignee_tasks(user).filter(project__isnull=True).count()
        project_open = _open_assignee_tasks(user).filter(project__isnull=False).count()
        total_open = personal_open + project_open
        if total_open:
            parts = []
            if personal_open:
                parts.append(f'{personal_open} việc cá nhân')
            if project_open:
                parts.append(f'{project_open} bước dự án')
            in_progress = _open_assignee_tasks(user).filter(
                status=WorkTask.STATUS_IN_PROGRESS,
            ).count()
            detail = ' · '.join(parts)
            if in_progress:
                detail += f' ({in_progress} đang làm)'
            widgets.append({
                'level': 'warning',
                'icon': 'bi-list-check',
                'title': 'Công việc chưa hoàn thành',
                'text': f'{detail} — xử lý đến khi hoàn thành.',
                'url': reverse('tasks:my') if personal_open else reverse('tasks:project_list'),
                'action': 'Xem việc',
                'badge': total_open,
            })

    if can_assign_tasks(user):
        pending_review = _assigner_pending_review_qs(user).count()
        if pending_review:
            widgets.append({
                'level': 'info',
                'icon': 'bi-check2-circle',
                'title': 'Công việc chờ duyệt',
                'text': f'{pending_review} việc / bước đã nộp — cần duyệt hoặc yêu cầu sửa.',
                'url': reverse('tasks:assigned') + '?status=pending_review',
                'action': 'Duyệt việc',
                'badge': pending_review,
            })

        rejected = _assigner_rejected_qs(user).count()
        if rejected:
            widgets.append({
                'level': 'warning',
                'icon': 'bi-arrow-repeat',
                'title': 'Việc bị từ chối',
                'text': f'{rejected} việc / bước bị từ chối — giao lại hoặc chọn người khác.',
                'url': reverse('tasks:assigned') + '?status=rejected',
                'action': 'Xử lý',
                'badge': rejected,
            })

        pending_handoffs = WorkTaskHandoff.objects.filter(
            project__owner=user,
            status=WorkTaskHandoff.STATUS_PENDING,
        ).count()
        if pending_handoffs:
            widgets.append({
                'level': 'info',
                'icon': 'bi-arrow-left-right',
                'title': 'Chuyển giao chờ duyệt',
                'text': f'{pending_handoffs} yêu cầu chuyển giao bước dự án cần bạn duyệt.',
                'url': reverse('tasks:project_list'),
                'action': 'Xem dự án',
                'badge': pending_handoffs,
            })

    return widgets


def _incomplete_assigned_courses_qs(user):
    from training.models import Course, Enrollment

    assigned_ids = Course.objects.filter(
        assigned_users=user,
        is_active=True,
    ).values_list('pk', flat=True)
    completed_ids = Enrollment.objects.filter(
        user=user,
        course_id__in=assigned_ids,
        is_completed=True,
    ).values_list('course_id', flat=True)
    return Course.objects.filter(pk__in=assigned_ids).exclude(pk__in=completed_ids)


def _pending_assigned_exams_qs(user):
    from assessment.models import Exam, ExamSubmission

    completed_ids = ExamSubmission.objects.filter(
        user=user,
        submitted_at__isnull=False,
    ).values_list('exam_id', flat=True)
    return Exam.objects.filter(
        assigned_users=user,
        is_active=True,
    ).exclude(pk__in=completed_ids).distinct()


def _training_widgets(user):
    if not user_can_access_module(user, MODULE_TRAINING):
        return []

    incomplete_qs = _incomplete_assigned_courses_qs(user)
    count = incomplete_qs.count()
    if not count:
        return []

    from training.models import Enrollment

    in_progress = 0
    for course in incomplete_qs:
        enrollment = Enrollment.objects.filter(user=user, course=course).first()
        if enrollment and enrollment.progress_percent > 0 and not enrollment.is_completed:
            in_progress += 1

    detail = f'{count} khóa được giao'
    if in_progress:
        detail += f' ({in_progress} đang học)'

    return [{
        'level': 'warning',
        'icon': 'bi-mortarboard-fill',
        'title': 'Khóa học chưa hoàn thành',
        'text': f'{detail} — học đến khi hoàn thành.',
        'url': reverse('my_courses'),
        'action': 'Vào học',
        'badge': count,
    }]


def _exam_widgets(user):
    if not user_can_access_module(user, MODULE_ASSESSMENT):
        return []

    pending_qs = _pending_assigned_exams_qs(user)
    count = pending_qs.count()
    if not count:
        return []

    now = timezone.now()
    open_count = pending_qs.filter(start_time__lte=now, end_time__gte=now).count()
    upcoming = pending_qs.filter(start_time__gt=now).count()
    overdue = pending_qs.filter(end_time__lt=now).count()

    parts = []
    if open_count:
        parts.append(f'{open_count} đang mở')
    if upcoming:
        parts.append(f'{upcoming} sắp mở')
    if overdue:
        parts.append(f'{overdue} quá hạn')

    detail = f'Còn {count} bài được giao'
    if parts:
        detail += f' ({", ".join(parts)})'
    detail += ' — hoàn thành để không còn nhắc.'

    return [{
        'level': 'warning',
        'icon': 'bi-journal-check',
        'title': 'Bài kiểm tra',
        'text': detail,
        'url': reverse('exam_list'),
        'action': 'Vào thi',
        'badge': count,
    }]


def _service_request_widgets(user):
    if not user_can_access_module(user, MODULE_SERVICE_REQUESTS):
        return []

    from service_requests.models import ServiceRequest
    from service_requests.permissions import pending_steps_for_user

    widgets = []

    my_open = ServiceRequest.objects.filter(
        requester=user,
        status=ServiceRequest.STATUS_IN_PROGRESS,
    ).count()
    if my_open:
        widgets.append({
            'level': 'info',
            'icon': 'bi-send-fill',
            'title': 'Yêu cầu đang xử lý',
            'text': f'{my_open} yêu cầu bạn gửi chưa hoàn thành — theo dõi tiến trình duyệt.',
            'url': reverse('service_requests:my') + '?status=in_progress',
            'action': 'Xem yêu cầu',
            'badge': my_open,
        })

    pending = pending_steps_for_user(user).count()
    if pending:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-inbox-fill',
            'title': 'Yêu cầu chờ xử lý',
            'text': f'{pending} bước cần bạn duyệt hoặc tiếp nhận.',
            'url': reverse('service_requests:pending'),
            'action': 'Xử lý',
            'badge': pending,
        })

    return widgets


def get_portal_dashboard(user):
    """Trả về danh sách widget nhắc việc (dict) cho trang chủ."""
    widgets = []
    today = timezone.localdate()

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

    widgets.extend(_task_widgets(user))
    widgets.extend(_training_widgets(user))
    widgets.extend(_exam_widgets(user))
    widgets.extend(_service_request_widgets(user))

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

    return widgets
