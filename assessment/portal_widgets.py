"""Tóm tắt việc cần làm — hiển thị trên trang chủ portal."""

from reports.navigation import redirect_team_legacy, team_pending_url_for_user, today_url_for_user
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
    get_team_report_members,
)
from hrm.module_permissions import (
    MODULE_ASSESSMENT,
    MODULE_DE_XUAT,
    MODULE_EQUIPMENT,
    MODULE_FEEDBACK,
    MODULE_HO_TRO,
    MODULE_TASKS,
    MODULE_TRAINING,
    user_can_access_module,
    user_can_edit_module,
)
from reports.models import DailyWorkReport, ReportComment
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


def get_training_pending_count(user) -> int:
    """Số khóa học được giao chưa hoàn thành — badge menu Đào tạo."""
    if not user_can_access_module(user, MODULE_TRAINING):
        return 0
    return _incomplete_assigned_courses_qs(user).count()


def get_assessment_pending_count(user) -> int:
    """Số bài kiểm tra được giao chưa nộp — badge menu Kiểm tra."""
    if not user_can_access_module(user, MODULE_ASSESSMENT):
        return 0
    return _pending_assigned_exams_qs(user).count()


def _training_widgets(user):
    if not user_can_access_module(user, MODULE_TRAINING):
        return []

    count = get_training_pending_count(user)
    if not count:
        return []

    incomplete_qs = _incomplete_assigned_courses_qs(user)

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

    count = get_assessment_pending_count(user)
    if not count:
        return []

    pending_qs = _pending_assigned_exams_qs(user)

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


def _de_xuat_widgets(user):
    if not user_can_access_module(user, MODULE_DE_XUAT):
        return []

    from service_requests.models import RequestType, ServiceRequest
    from service_requests.permissions import pending_steps_for_user

    widgets = []

    my_open = ServiceRequest.objects.filter(
        requester=user,
        status=ServiceRequest.STATUS_IN_PROGRESS,
        request_type__code=RequestType.CODE_ASSET_PURCHASE,
    ).count()
    if my_open:
        widgets.append({
            'level': 'info',
            'icon': 'bi-lightbulb-fill',
            'title': 'Đề xuất đang xử lý',
            'text': f'{my_open} đề xuất bạn gửi chưa hoàn thành — theo dõi tiến trình duyệt.',
            'url': reverse('service_requests:de_xuat_my') + '?status=in_progress',
            'action': 'Xem đề xuất',
            'badge': my_open,
        })

    pending = pending_steps_for_user(user).filter(
        request__request_type__code=RequestType.CODE_ASSET_PURCHASE,
    ).count()
    if pending:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-inbox-fill',
            'title': 'Đề xuất chờ xử lý',
            'text': f'{pending} bước cần bạn duyệt hoặc tiếp nhận.',
            'url': reverse('service_requests:de_xuat_pending'),
            'action': 'Xử lý',
            'badge': pending,
        })

    return widgets


def _ho_tro_widgets(user):
    if not user_can_access_module(user, MODULE_HO_TRO):
        return []

    from service_requests.models import RequestType, ServiceRequest
    from service_requests.permissions import pending_steps_for_user

    widgets = []

    my_open = ServiceRequest.objects.filter(
        requester=user,
        status=ServiceRequest.STATUS_IN_PROGRESS,
        request_type__code=RequestType.CODE_IT_REPAIR,
    ).count()
    if my_open:
        widgets.append({
            'level': 'info',
            'icon': 'bi-tools',
            'title': 'Hỗ trợ đang xử lý',
            'text': f'{my_open} yêu cầu hỗ trợ chưa hoàn thành.',
            'url': reverse('service_requests:ho_tro_my') + '?status=in_progress',
            'action': 'Xem yêu cầu',
            'badge': my_open,
        })

    pending = pending_steps_for_user(user).filter(
        request__request_type__code=RequestType.CODE_IT_REPAIR,
    ).count()
    if pending:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-inbox-fill',
            'title': 'Hỗ trợ chờ xử lý',
            'text': f'{pending} bước cần bạn duyệt hoặc xác nhận.',
            'url': reverse('service_requests:ho_tro_pending'),
            'action': 'Xử lý',
            'badge': pending,
        })

    return widgets


def _equipment_it_widgets(user):
    if not user_can_access_module(user, MODULE_EQUIPMENT):
        return []

    from django.db.utils import DatabaseError, OperationalError, ProgrammingError

    from equipment.services.it_repair_queue import pending_it_repair_steps_for_user

    try:
        pending = pending_it_repair_steps_for_user(user).count()
    except (ProgrammingError, OperationalError, DatabaseError):
        return []
    if not pending:
        return []
    return [{
        'level': 'warning',
        'icon': 'bi-tools',
        'title': 'Hỗ trợ kỹ thuật',
        'text': f'{pending} sự cố chờ IT xử lý trong Quản lý thiết bị.',
        'url': reverse('equipment:it_repair_list_it'),
        'action': 'Xử lý',
        'badge': pending,
    }]


def _feedback_widgets(user):
    from hrm.module_permissions import user_can_update_module

    if not user_can_update_module(user, MODULE_FEEDBACK):
        return []

    from feedback.models import Feedback

    unviewed = Feedback.objects.filter(viewed_at__isnull=True).count()
    if not unviewed:
        return []
    return [{
        'level': 'warning',
        'icon': 'bi-chat-square-text-fill',
        'title': 'Góp ý chưa xem',
        'text': f'Còn {unviewed} góp ý chưa xem — mở danh sách để đọc.',
        'url': reverse('feedback:list'),
        'action': 'Xem góp ý',
        'badge': unviewed,
    }]


def _utilities_widgets(user):
    try:
        from utilities.reminders import get_utilities_portal_widgets
        return get_utilities_portal_widgets(user)
    except Exception:
        return []


def _report_comment_widgets(user):
    """Widget nhận xét báo cáo chưa đọc — cho cả nhân viên (quản lý nhận xét) và quản lý (NV phản hồi)."""
    widgets = []

    # Nhận xét chưa đọc trên báo cáo CỦA MÌNH (quản lý nhận xét cho mình)
    my_daily = (
        ReportComment.objects.filter(is_read=False, daily_report__employee=user)
        .exclude(author=user)
        .values_list('daily_report_id', flat=True)
        .first()
    )
    my_weekly = (
        ReportComment.objects.filter(is_read=False, weekly_report__employee=user)
        .exclude(author=user)
        .values_list('weekly_report_id', flat=True)
        .first()
    ) if not my_daily else None

    if my_daily:
        from reports.models import DailyWorkReport as _DWR
        try:
            r = _DWR.objects.select_related('employee', 'employee__profile').get(pk=my_daily)
            url = reverse(
                'reports:detail_cn' if r.is_production_report else 'reports:detail_vp',
                args=[r.pk],
            )
            report_date_str = r.report_date.strftime('%d/%m/%Y')
        except _DWR.DoesNotExist:
            url = reverse('reports:my_vp')
            report_date_str = ''
        my_unread = ReportComment.objects.filter(
            is_read=False, daily_report__employee=user,
        ).exclude(author=user).count() + ReportComment.objects.filter(
            is_read=False, weekly_report__employee=user,
        ).exclude(author=user).count()
        if my_unread == 1 and report_date_str:
            text = f'Bạn có nhận xét mới từ quản lý trên báo cáo ngày {report_date_str}.'
        else:
            text = f'Bạn có {my_unread} nhận xét mới từ quản lý.'
        widgets.append({
            'level': 'info',
            'icon': 'bi-chat-dots-fill',
            'title': 'Nhận xét báo cáo',
            'text': text,
            'url': url,
            'action': 'Xem',
            'badge': my_unread,
        })
    elif my_weekly:
        url = reverse('reports:weekly_detail_vp', args=[my_weekly])
        my_unread = ReportComment.objects.filter(
            is_read=False, weekly_report__employee=user,
        ).exclude(author=user).count()
        if my_unread == 1:
            from reports.models import WeeklyWorkReport as _WWR2
            try:
                wr = _WWR2.objects.get(pk=my_weekly)
                text = f'Bạn có nhận xét mới từ quản lý trên báo cáo tuần {wr.week_start.strftime("%d/%m/%Y")}.'
            except _WWR2.DoesNotExist:
                text = f'Bạn có {my_unread} nhận xét mới từ quản lý.'
        else:
            text = f'Bạn có {my_unread} nhận xét mới từ quản lý.'
        widgets.append({
            'level': 'info',
            'icon': 'bi-chat-dots-fill',
            'title': 'Nhận xét báo cáo',
            'text': text,
            'url': url,
            'action': 'Xem',
            'badge': my_unread,
        })

    # Phản hồi chưa đọc trên báo cáo CẤP DƯỚI (nhân viên phản hồi lại)
    if can_view_team_reports(user):
        team_ids = list(get_team_report_members(user).values_list('pk', flat=True))
        if team_ids:
            sub_daily = (
                ReportComment.objects.filter(
                    is_read=False,
                    daily_report__employee_id__in=team_ids,
                    author_id__in=team_ids,
                ).values_list('daily_report_id', flat=True).first()
            )
            sub_weekly = (
                ReportComment.objects.filter(
                    is_read=False,
                    weekly_report__employee_id__in=team_ids,
                    author_id__in=team_ids,
                ).values_list('weekly_report_id', flat=True).first()
            ) if not sub_daily else None

            if sub_daily:
                from reports.models import DailyWorkReport as _DWR2
                try:
                    r = _DWR2.objects.select_related('employee', 'employee__profile').get(pk=sub_daily)
                    url = reverse(
                        'reports:detail_cn' if r.is_production_report else 'reports:detail_vp',
                        args=[r.pk],
                    )
                    emp_name = r.employee.profile.full_name if hasattr(r.employee, 'profile') and r.employee.profile.full_name else r.employee.username
                    report_date_str = r.report_date.strftime('%d/%m/%Y')
                except _DWR2.DoesNotExist:
                    url = reverse('reports:team_vp')
                    emp_name = 'nhân viên'
                    report_date_str = ''
                sub_unread = ReportComment.objects.filter(
                    is_read=False, daily_report__employee_id__in=team_ids, author_id__in=team_ids,
                ).count() + ReportComment.objects.filter(
                    is_read=False, weekly_report__employee_id__in=team_ids, author_id__in=team_ids,
                ).count()
                if sub_unread == 1 and report_date_str:
                    text = f'Bạn có phản hồi từ báo cáo {report_date_str} của {emp_name}.'
                else:
                    text = f'Bạn có {sub_unread} phản hồi mới từ nhân viên.'
                widgets.append({
                    'level': 'info',
                    'icon': 'bi-chat-dots-fill',
                    'title': 'Phản hồi báo cáo',
                    'text': text,
                    'url': url,
                    'action': 'Xem',
                    'badge': sub_unread,
                })
            elif sub_weekly:
                from reports.models import WeeklyWorkReport as _WWR
                try:
                    wr = _WWR.objects.select_related('employee', 'employee__profile').get(pk=sub_weekly)
                    url = reverse('reports:weekly_detail_vp', args=[sub_weekly])
                    emp_name = wr.employee.profile.full_name if hasattr(wr.employee, 'profile') and wr.employee.profile.full_name else wr.employee.username
                    report_date_str = wr.week_start.strftime('%d/%m/%Y')
                except _WWR.DoesNotExist:
                    url = reverse('reports:team_vp')
                    emp_name = 'nhân viên'
                    report_date_str = ''
                sub_unread = ReportComment.objects.filter(
                    is_read=False, weekly_report__employee_id__in=team_ids, author_id__in=team_ids,
                ).count()
                if sub_unread == 1 and report_date_str:
                    text = f'Bạn có phản hồi từ báo cáo tuần {report_date_str} của {emp_name}.'
                else:
                    text = f'Bạn có {sub_unread} phản hồi mới từ nhân viên.'
                widgets.append({
                    'level': 'info',
                    'icon': 'bi-chat-dots-fill',
                    'title': 'Phản hồi báo cáo',
                    'text': text,
                    'url': url,
                    'action': 'Xem',
                    'badge': sub_unread,
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
                'url': today_url_for_user(user),
                'action': 'Nhập báo cáo',
            })

    widgets.extend(_task_widgets(user))
    widgets.extend(_training_widgets(user))
    widgets.extend(_exam_widgets(user))
    widgets.extend(_de_xuat_widgets(user))
    widgets.extend(_ho_tro_widgets(user))
    widgets.extend(_equipment_it_widgets(user))
    widgets.extend(_feedback_widgets(user))
    widgets.extend(_utilities_widgets(user))
    widgets.extend(_report_comment_widgets(user))

    # --- HOD / GM: team chưa nộp BC ---
    if can_view_team_reports(user):
        team_users = get_team_report_members(user)
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
                    'url': team_pending_url_for_user(user),
                    'action': 'Xem team',
                    'badge': missing,
                })

    return widgets
