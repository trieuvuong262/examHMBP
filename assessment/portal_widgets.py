"""Tóm tắt việc cần làm — hiển thị trên trang chủ portal."""

from reports.navigation import (
    preferred_daily_report_profile,
    redirect_team_legacy,
    team_pending_url_for_user,
    today_url_for_user,
)
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
    MODULE_SAN_XUAT,
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
        request_type__code__in=[RequestType.CODE_ASSET_PURCHASE, RequestType.CODE_GENERAL_PROPOSAL],
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
        request__request_type__code__in=[RequestType.CODE_ASSET_PURCHASE, RequestType.CODE_GENERAL_PROPOSAL],
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


def _san_xuat_widgets(user):
    """Nhắc việc sản xuất: lệnh trễ hạn, lệnh sắp tới hạn, NPL chưa về (P4)."""
    if not user_can_access_module(user, MODULE_SAN_XUAT):
        return []

    from django.db.utils import DatabaseError, OperationalError, ProgrammingError

    try:
        from san_xuat.hub_models import SxProductionOrder, SxPurchaseOrder
        from san_xuat.services.sx_settings import sx_int
    except ImportError:
        return []

    today = timezone.localdate()
    widgets = []
    open_statuses = (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
    )

    try:
        horizon_days = sx_int('mo_late_alert_days', 3, min_v=0, max_v=60)
        open_mos = list(
            SxProductionOrder.objects.filter(is_demo=False, status__in=open_statuses)
            .only('code', 'qty', 'qty_done', 'due_date', 'planned_end')
        )
        open_pos = list(
            SxPurchaseOrder.objects.filter(
                is_demo=False,
                status=SxPurchaseOrder.STATUS_CONFIRMED,
                expected_date__lt=today,
            ).prefetch_related('lines')
        )
    except (ProgrammingError, OperationalError, DatabaseError):
        return []

    late = []
    soon = []
    for mo in open_mos:
        deadline = mo.due_date or mo.planned_end
        if not deadline:
            continue
        if (mo.qty_done or 0) >= (mo.qty or 0):
            continue
        if deadline < today:
            late.append(mo)
        elif (deadline - today).days <= horizon_days:
            soon.append(mo)

    if late:
        sample = ', '.join(mo.code for mo in late[:3])
        widgets.append({
            'level': 'danger',
            'icon': 'bi-exclamation-octagon-fill',
            'title': 'Lệnh sản xuất trễ hạn',
            'text': f'{len(late)} lệnh đã quá hạn mà chưa hoàn thành ({sample}).',
            'url': reverse('san_xuat:dispatch_mo') + '?status=in_progress',
            'action': 'Xem lệnh',
            'badge': len(late),
        })
    if soon:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-hourglass-split',
            'title': 'Lệnh sản xuất sắp tới hạn',
            'text': f'{len(soon)} lệnh tới hạn trong {horizon_days} ngày tới.',
            'url': reverse('san_xuat:dispatch_mo'),
            'action': 'Xem lệnh',
            'badge': len(soon),
        })

    pending_pos = [
        po for po in open_pos
        if any((ln.qty_ordered or 0) > (ln.qty_received or 0) for ln in po.lines.all())
    ]
    if pending_pos:
        sample = ', '.join(po.code for po in pending_pos[:3])
        widgets.append({
            'level': 'warning',
            'icon': 'bi-truck',
            'title': 'Nguyên phụ liệu chưa về',
            'text': f'{len(pending_pos)} đơn mua hàng đã quá ngày hàng về dự kiến ({sample}).',
            'url': reverse('san_xuat:purchase_order'),
            'action': 'Xem đơn mua',
            'badge': len(pending_pos),
        })

    return widgets


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
        # Lấy comment đầu tiên chưa đọc để biết tên quản lý
        first_comment = (
            ReportComment.objects.filter(is_read=False, daily_report__employee=user)
            .exclude(author=user)
            .select_related('author', 'author__profile', 'daily_report')
            .first()
        )
        try:
            r = _DWR.objects.get(pk=my_daily)
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
        if my_unread == 1 and report_date_str and first_comment:
            manager_name = first_comment.author.profile.full_name if hasattr(first_comment.author, 'profile') and first_comment.author.profile.full_name else first_comment.author.username
            text = f'Bạn có nhận xét mới từ {manager_name} cho báo cáo ngày {report_date_str}.'
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
            first_wk_comment = (
                ReportComment.objects.filter(is_read=False, weekly_report__employee=user)
                .exclude(author=user)
                .select_related('author', 'author__profile', 'weekly_report')
                .first()
            )
            try:
                wr = _WWR2.objects.get(pk=my_weekly)
                manager_name = first_wk_comment.author.profile.full_name if first_wk_comment and hasattr(first_wk_comment.author, 'profile') and first_wk_comment.author.profile.full_name else 'quản lý'
                text = f'Bạn có nhận xét mới từ {manager_name} cho báo cáo tuần {wr.week_start.strftime("%d/%m/%Y")}.'
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


def _sample_names(names, total: int) -> str:
    shown = [name for name in names if name]
    if not shown:
        return ''
    text = ', '.join(shown)
    if total > len(shown):
        text += '…'
    return f' ({text})'


def _recruitment_widgets(user):
    """Việc trên menu Đánh giá ứng viên: CV, kết quả PV đã tới giờ, giám đốc duyệt."""
    import logging

    try:
        return _recruitment_widget_items(user)
    except Exception:
        logging.getLogger(__name__).warning('recruitment portal widgets failed', exc_info=True)
        return []


def _recruitment_widget_items(user):
    from recruitment.models import Candidate, JobPosting
    from recruitment.permissions import (
        can_final_approve,
        final_queue,
        interview_queue,
        is_hiring_manager,
        manager_job_filter,
    )

    widgets = []
    if is_hiring_manager(user):
        pending_cv = (
            Candidate.objects.filter(
                status=Candidate.STATUS_REVIEWING,
                job_posting__in=JobPosting.objects.filter(manager_job_filter(user)),
            )
            .exclude(job_posting__skip_cv_review=True)
            .exclude(reviews__reviewer=user)
        )
        cv_count = pending_cv.count()
        if cv_count:
            names = list(pending_cv.order_by('status_changed_at', 'pk').values_list('full_name', flat=True)[:3])
            widgets.append({
                'level': 'warning',
                'icon': 'bi-person-lines-fill',
                'title': 'Tuyển dụng — đánh giá CV',
                'text': f'{cv_count} hồ sơ đang chờ bạn đánh giá{_sample_names(names, cv_count)}.',
                'url': reverse('recruitment_review_list') + '?tab=cho-danh-gia',
                'action': 'Đánh giá',
                'badge': cv_count,
            })

    due_interviews = interview_queue(user).filter(interview__interview_time__lte=timezone.now())
    due_count = due_interviews.count()
    if due_count:
        names = list(due_interviews.order_by('interview__interview_time').values_list('full_name', flat=True)[:3])
        widgets.append({
            'level': 'warning',
            'icon': 'bi-camera-video',
            'title': 'Tuyển dụng — kết quả phỏng vấn',
            'text': f'{due_count} buổi phỏng vấn đã tới giờ, đang chờ bạn nhập kết quả{_sample_names(names, due_count)}.',
            'url': reverse('recruitment_review_list') + '?tab=phong-van',
            'action': 'Nhập kết quả',
            'badge': due_count,
        })

    if can_final_approve(user):
        finals = final_queue(user).order_by('status_changed_at', 'pk')
        final_count = finals.count()
        if final_count:
            names = list(finals.values_list('full_name', flat=True)[:3])
            widgets.append({
                'level': 'warning',
                'icon': 'bi-patch-check-fill',
                'title': 'Tuyển dụng — chờ giám đốc duyệt',
                'text': f'{final_count} hồ sơ phỏng vấn Đạt đang chờ bạn duyệt{_sample_names(names, final_count)}.',
                'url': reverse('recruitment_review_list') + '?tab=giam-doc-duyet',
                'action': 'Duyệt',
                'badge': final_count,
            })
    return widgets


def _thiet_ke_sp_widgets(user):
    from hrm.module_permissions import MODULE_THIET_KE_SP, user_can_access_module
    from thiet_ke_sp.context_processors import member_only_access, user_badges

    if not user_can_access_module(user, MODULE_THIET_KE_SP) and not member_only_access(user):
        return []

    from thiet_ke_sp.models import ProductDevelopment, Role, Task
    from thiet_ke_sp.presenters import APPROVAL_STATUSES

    badges = user_badges(user)
    widgets = []
    task_url = reverse('thiet_ke_sp:my_tasks')
    approve = badges.get('approve') or 0
    # Việc duyệt có thẻ riêng — không đếm lại trong «việc cần làm».
    work = Task.objects.filter(assignee=user, state=Task.STATE_OPEN).exclude(
        dossier__status__in=('paused', 'cancelled', 'closed'),
    )
    if approve:
        work = work.exclude(role=Role.APPROVER, dossier__status__in=APPROVAL_STATUSES)
    overdue = work.filter(due_at__lt=timezone.now()).count()
    pending = work.count() - overdue
    if overdue:
        widgets.append({
            'level': 'danger',
            'icon': 'bi-palette-fill',
            'title': 'Thiết kế sản phẩm — quá hạn',
            'text': f'{overdue} việc hồ sơ thiết kế đã quá hạn.',
            'url': task_url,
            'action': 'Xử lý',
            'badge': overdue,
        })
    if pending > 0:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-palette',
            'title': 'Thiết kế sản phẩm — việc cần làm',
            'text': f'{pending} việc hồ sơ thiết kế đang chờ bạn xử lý.',
            'url': task_url,
            'action': 'Xem',
            'badge': pending,
        })
    if approve:
        names = list(
            ProductDevelopment.objects.filter(approver=user, status__in=APPROVAL_STATUSES)
            .order_by('status_changed_at', 'pk')
            .values_list('name', flat=True)[:3]
        )
        widgets.append({
            'level': 'warning',
            'icon': 'bi-check2-circle',
            'title': 'Thiết kế sản phẩm — chờ duyệt',
            'text': f'{approve} hồ sơ đang chờ bạn duyệt{_sample_names(names, approve)}.',
            'url': reverse('thiet_ke_sp:approve_queue'),
            'action': 'Duyệt',
            'badge': approve,
        })
    if badges['unread'] and not widgets:
        widgets.append({
            'level': 'info',
            'icon': 'bi-palette',
            'title': 'Thiết kế sản phẩm',
            'text': f'{badges["unread"]} thông báo trên hồ sơ bạn được giao xem.',
            'url': reverse('thiet_ke_sp:notifications'),
            'action': 'Xem',
            'badge': badges['unread'],
        })
    return widgets


def _ra_mat_sp_widgets(user):
    from hrm.module_permissions import MODULE_RA_MAT_SP, user_can_access_module
    from ra_mat_sp.context_processors import user_badges
    from ra_mat_sp.permissions import has_participation

    if not user_can_access_module(user, MODULE_RA_MAT_SP) and not has_participation(user):
        return []

    badges = user_badges(user)
    widgets = []
    task_url = reverse('ra_mat_sp:my_tasks')
    if badges['overdue']:
        widgets.append({
            'level': 'danger',
            'icon': 'bi-rocket-takeoff-fill',
            'title': 'Kế hoạch ra mắt — quá hạn',
            'text': f'{badges["overdue"]} việc ra mắt đã quá hạn.',
            'url': task_url,
            'action': 'Xử lý',
            'badge': badges['overdue'],
        })
    pending = badges['tasks'] - badges['overdue']
    if pending > 0:
        widgets.append({
            'level': 'warning',
            'icon': 'bi-rocket-takeoff',
            'title': 'Kế hoạch ra mắt — việc cần làm',
            'text': f'{pending} việc ra mắt đang chờ bạn xử lý.',
            'url': task_url,
            'action': 'Xem',
            'badge': pending,
        })
    if badges.get('approve'):
        widgets.append({
            'level': 'warning',
            'icon': 'bi-check2-circle',
            'title': 'Kế hoạch ra mắt — chờ phê duyệt',
            'text': f'{badges["approve"]} kế hoạch đang chờ bạn phê duyệt.',
            'url': reverse('ra_mat_sp:approve_queue'),
            'action': 'Duyệt',
            'badge': badges['approve'],
        })
    return widgets


PORTAL_BADGE_CACHE_SECONDS = 60


def portal_badge_counts(user) -> dict:
    """Ba con số badge trên thanh tiêu đề — cache ngắn hạn.

    ``jp_portal_todo_count`` trước đây được tính bằng cách chạy toàn bộ
    ``get_portal_dashboard`` trên MỌI request (hàng chục truy vấn qua nhiều
    module) chỉ để hiện một con số. Nay cache 60 giây theo user, nên badge có
    thể chậm tối đa 1 phút — đổi lại mỗi trang tiết kiệm rất nhiều truy vấn.
    Trang chủ vẫn gọi ``get_portal_dashboard`` trực tiếp nên danh sách việc
    cần làm luôn là dữ liệu mới.
    """
    from django.core.cache import cache

    pk = getattr(user, 'pk', None)
    if not pk:
        return {'todo': 0, 'training': 0, 'assessment': 0}

    key = f'jp:badges:{pk}'
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        counts = {
            'todo': len(get_portal_dashboard(user)),
            'training': get_training_pending_count(user),
            'assessment': get_assessment_pending_count(user),
        }
    except Exception:
        counts = {'todo': 0, 'training': 0, 'assessment': 0}
    cache.set(key, counts, PORTAL_BADGE_CACHE_SECONDS)
    return counts


def invalidate_portal_badges(user) -> None:
    """Xoá cache badge — gọi khi vừa đổi trạng thái việc cần làm của user."""
    from django.core.cache import cache

    pk = getattr(user, 'pk', None)
    if pk:
        cache.delete(f'jp:badges:{pk}')


_LEVEL_RANK = {'danger': 0, 'warning': 1, 'info': 2}

# Nhóm trên trang chủ: nhãn, icon, thứ tự khi cùng mức gấp.
_PORTAL_GROUPS = {
    'announcements': ('Thông báo', 'bi-megaphone', 10),
    'recruitment': ('Tuyển dụng', 'bi-person-badge', 20),
    'exams': ('Bài kiểm tra', 'bi-journal-check', 30),
    'reports': ('Báo cáo', 'bi-clipboard-check', 40),
    'design': ('Thiết kế sản phẩm', 'bi-palette', 50),
    'production': ('Sản xuất', 'bi-gear-wide-connected', 60),
    'launch': ('Kế hoạch ra mắt', 'bi-rocket-takeoff', 70),
    'tasks': ('Việc cần làm', 'bi-list-check', 80),
    'requests': ('Đề xuất', 'bi-send', 90),
    'support': ('Hỗ trợ', 'bi-life-preserver', 100),
    'equipment': ('Thiết bị', 'bi-pc-display', 110),
    'training': ('Đào tạo', 'bi-mortarboard', 120),
    'feedback': ('Góp ý', 'bi-chat-square-text', 130),
    'utilities': ('Tiện ích', 'bi-grid', 140),
}


def _mark_group(items, group):
    for item in items:
        item['group'] = group
    return items


def _short_label(title: str, group_label: str) -> str:
    prefix = f'{group_label} — '
    if title.startswith(prefix):
        return title[len(prefix):]
    if ' — ' in title:
        head, tail = title.split(' — ', 1)
        if head == group_label:
            return tail
    return title


def group_portal_dashboard(widgets):
    """Gộp widget cùng module, việc gấp xếp trước."""
    buckets = {}
    seen = []
    for item in widgets:
        key = item.get('group') or 'other'
        if key not in buckets:
            buckets[key] = []
            seen.append(key)
        buckets[key].append(item)

    groups = []
    for key in seen:
        items = buckets[key]
        items.sort(key=lambda it: _LEVEL_RANK.get(it.get('level'), 9))
        label, icon, seq = _PORTAL_GROUPS.get(key, ('Việc khác', 'bi-dot', 500))
        worst = min(_LEVEL_RANK.get(it.get('level'), 9) for it in items)
        badge_sum = sum(int(it['badge']) for it in items if it.get('badge'))
        for it in items:
            it['label'] = _short_label(it.get('title') or '', label)
        groups.append({
            'key': key,
            'label': label,
            'icon': icon,
            'level': next((name for name, rank in _LEVEL_RANK.items() if rank == worst), 'info'),
            'items': items,
            'badge': badge_sum or len(items),
            'single': len(items) == 1,
            'has_links': any(not it.get('dismiss_url') for it in items),
            '_sort': seq,
        })
    groups.sort(key=lambda g: g['_sort'])
    return groups


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
            'group': 'announcements',
        })

    # --- Báo cáo hôm nay (cá nhân — không áp dụng Giám đốc) ---
    if can_submit_daily_report(user):
        today_report_qs = DailyWorkReport.objects.filter(
            employee=user,
            report_date=today,
        )
        widget_profile = preferred_daily_report_profile(user)
        if widget_profile:
            today_report_qs = today_report_qs.filter(report_profile=widget_profile)
        today_report = today_report_qs.first()
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
                'group': 'reports',
            })

    widgets.extend(_mark_group(_task_widgets(user), 'tasks'))
    widgets.extend(_mark_group(_recruitment_widgets(user), 'recruitment'))
    widgets.extend(_mark_group(_training_widgets(user), 'training'))
    widgets.extend(_mark_group(_exam_widgets(user), 'exams'))
    widgets.extend(_mark_group(_de_xuat_widgets(user), 'requests'))
    widgets.extend(_mark_group(_ho_tro_widgets(user), 'support'))
    widgets.extend(_mark_group(_equipment_it_widgets(user), 'equipment'))
    widgets.extend(_mark_group(_feedback_widgets(user), 'feedback'))
    widgets.extend(_mark_group(_utilities_widgets(user), 'utilities'))
    widgets.extend(_mark_group(_san_xuat_widgets(user), 'production'))
    widgets.extend(_mark_group(_thiet_ke_sp_widgets(user), 'design'))
    widgets.extend(_mark_group(_ra_mat_sp_widgets(user), 'launch'))
    widgets.extend(_mark_group(_report_comment_widgets(user), 'reports'))

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
                    'group': 'reports',
                })

    return widgets
