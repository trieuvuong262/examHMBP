import logging
import os
import uuid
from datetime import datetime, timedelta
from urllib.parse import unquote, urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib import messages
from django.db.models import Count, Exists, OuterRef, Sum, Q

from assessment.decorators import module_perm_required

logger = logging.getLogger(__name__)
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import (
    can_review_user_report,
    can_review_user_weekly_report,
    can_submit_daily_report,
    can_view_team_reports,
    can_view_user_report,
    can_view_user_weekly_report,
    get_team_report_members,
    is_director,
)
from hrm.user_search import filter_users_by_division
from PortalJustPlay.list_search import apply_combined_search, apply_term_search, apply_user_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from reports.report_profile import (
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
    filter_team_members_for_report_profile,
)
from reports.production_shift_policy import PRODUCTION_SHIFT_ORDER, shift_badge_class
from reports.period_utils import (
    PERIOD_CHOICES,
    PERIOD_DAY,
    PERIOD_MONTH,
    PERIOD_WEEK,
    anchor_date_for_period,
    first_day_of_month,
    parse_office_period,
    parse_period_anchor_date,
    period_date_input_name,
    period_date_input_type,
    period_date_input_value,
    period_intro_title,
    period_date_label,
    period_nav_date,
    period_query_param,
    parse_team_date_range,
    parse_team_period_filter,
    team_date_range_query_params,
    team_range_query_params,
    TEAM_MANAGEMENT_DEFAULT_SPAN_DAYS,
    _parse_iso_date,
)
from reports.report_lock import (
    can_edit_own_daily_report,
    can_edit_own_weekly_report,
    is_report_edit_expired,
    is_report_locked,
    last_editable_date,
    lock_report_on_supervisor_view,
    report_edit_denied_message,
)
from reports.office_content import CKEDITOR_INLINE_PREFIX
from reports.daily_inline_images import (
    can_view_inline_image,
    inline_image_exists,
    is_inline_image_relpath,
    open_inline_image,
    parse_upload_report_date,
    save_inline_image,
)
from reports.navigation import (
    copy_prev_week_url_name_for_profile,
    detail_export_url_for_report,
    detail_url_for_report,
    history_url_for,
    list_back_url_for,
    team_list_back_url_for,
    team_list_query_from_request,
    can_view_own_report_history,
    page_tools_context_for_profile,
    redirect_copy_prev_week_legacy,
    redirect_team_legacy,
    redirect_team_weekly_legacy,
    report_profile_label,
    today_url_for_user,
    today_url_name_for_user,
    team_url_for_profile,
    team_weekly_url_name_for_profile,
    my_url_for_profile,
    my_url_for_user,
    my_url_name_for_profile,
    redirect_copy_yesterday_legacy,
    team_url_name_for_profile,
    weekly_detail_url_name_for_profile,
    weekly_url_for_profile,
    weekly_url_for_user,
    weekly_url_name_for_profile,
)
from reports.nas_health import mark_storage_unavailable
from reports.nas_pending import count_pending as count_pending_nas_sync
from reports.nas_pending_sync import maybe_auto_sync, sync_all_pending
from reports.week_utils import monday_of, parse_week_start, week_end, week_label

from .forms import (
    DailyWorkReportForm,
    DailyWorkReportLineFormSet,
    OfficeDailyWorkReportForm,
    WeeklyWorkReportForm,
)
from .models import (
    DailyWorkReport,
    DailyWorkReportAttachment,
    DailyWorkReportEditLog,
    ReportComment,
    ReportCommentAttachment,
    WeeklyWorkReport,
    WeeklyWorkReportAttachment,
)
from .team_sort import (
    build_team_table_columns,
    resolve_team_sort,
    sort_team_department_groups,
)
from .production_team import (
    build_production_day_shift_tabs,
    build_production_reports_by_employee,
    build_production_summary_shift_tabs,
    build_production_team_department_groups,
    production_team_review_row_counts,
    production_team_row_is_submitted,
    production_team_row_matches_filter,
    production_team_status_counts,
    query_production_team_reports,
)
from .team_utils import (
    build_report_team_department_groups,
    build_vp_team_department_groups,
    query_team_office_reports_in_range,
    daily_report_visible_to_team,
    department_filter_choices,
    division_filter_choices_from_team,
    meaningful_daily_reports_qs,
    meaningful_weekly_reports_qs,
    weekly_report_visible_to_team,
)
from .weekly_preview import file_attachment_preview, link_preview_rows
from .daily_nas_storage import (
    daily_attachment_abs_path,
    open_daily_attachment,
)
from .daily_uploads import copy_daily_attachments, save_daily_uploads
from .weekly_nas_storage import open_weekly_attachment, weekly_attachment_abs_path
from .weekly_uploads import copy_weekly_attachments, save_weekly_uploads, weekly_report_has_content

User = get_user_model()


_CK5_IMAGE_TYPES = frozenset({
    'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/png', 'image/gif', 'image/webp',
    'image/bmp', 'image/x-ms-bmp', 'image/x-png',
})
_CK5_IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'})
_CK5_MAX_BYTES = 5 * 1024 * 1024


def _ckeditor_upload_error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({'uploaded': 0, 'error': {'message': message}}, status=status)


def _is_allowed_ckeditor_image(upload) -> bool:
    content_type = (getattr(upload, 'content_type', '') or '').split(';')[0].strip().lower()
    if content_type in _CK5_IMAGE_TYPES:
        return True
    # Paste ảnh đôi khi gửi application/octet-stream hoặc thiếu content-type.
    if content_type in ('', 'application/octet-stream'):
        ext = os.path.splitext(getattr(upload, 'name', '') or '')[1].lower()
        return ext in _CK5_IMAGE_EXTS or not ext
    return False


def _reports_access_required(view_func):
    return module_perm_required(MODULE_REPORTS, 'view')(view_func)


_WEEKLY_SUBMIT_VIEWS = frozenset({
    'weekly_report_redirect',
    'weekly_report_cn',
    'weekly_report_vp',
    'copy_prev_week_redirect',
    'copy_prev_week_cn',
    'copy_prev_week_vp',
})


def _is_supervisor_entry_request(request):
    """Cấp trên nhập báo cáo hộ NV (?for_user=)."""
    from reports.production_hourly import can_proxy_enter_daily_report

    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    if not for_user_id:
        return False
    try:
        target = get_team_report_members(request.user).get(pk=int(for_user_id))
    except (ValueError, TypeError, User.DoesNotExist):
        return False
    return can_proxy_enter_daily_report(request.user, target)


def _require_submit_access(view_func):
    @module_perm_required(MODULE_REPORTS, 'create')
    def wrapper(request, *args, **kwargs):
        if not can_submit_daily_report(request.user):
            if can_view_team_reports(request.user):
                if view_func.__name__ in _WEEKLY_SUBMIT_VIEWS:
                    return redirect(redirect_team_weekly_legacy(request.user))
                return redirect(redirect_team_legacy(request.user))
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _require_today_report_access(view_func):
    """NV nộp báo cáo của mình; cấp trên nhập hộ qua ?for_user=."""
    @module_perm_required(MODULE_REPORTS, 'view')
    def wrapper(request, *args, **kwargs):
        from hrm.module_permissions import MODULE_REPORTS, user_can_create_module

        if _is_supervisor_entry_request(request):
            return view_func(request, *args, **kwargs)

        if not can_submit_daily_report(request.user):
            if can_view_team_reports(request.user):
                return redirect(redirect_team_legacy(request.user))
            return redirect('home_portal')
        if request.method == 'POST' and not user_can_create_module(request.user, MODULE_REPORTS):
            messages.error(request, 'Bạn không có quyền nộp báo cáo.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@_reports_access_required
def report_hub(request):
    target = redirect_team_legacy(request.user) if can_view_team_reports(request.user) and is_director(request.user) else None
    if target is None and can_submit_daily_report(request.user):
        target = today_url_for_user(request.user)
    if target is None and can_view_team_reports(request.user):
        target = redirect_team_legacy(request.user)
    if target:
        return redirect(target)
    messages.warning(
        request,
        'Chưa có quyền báo cáo. Liên hệ HR nếu bạn cần nộp hoặc duyệt báo cáo.',
    )
    return redirect('home_portal')


def _parse_report_date(request):
    report_date = request.GET.get('date') or request.POST.get('report_date') or timezone.localdate()
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
    return report_date


def _report_context_common(request, report_date, *, report_profile=None, report_period=PERIOD_DAY):
    yesterday = report_date - timedelta(days=1)
    prev_week = report_date - timedelta(days=7)
    if report_period == PERIOD_MONTH:
        prev_anchor = first_day_of_month(
            (report_date.replace(day=1) - timedelta(days=1))
        )
    elif report_period == PERIOD_WEEK:
        prev_anchor = prev_week
    else:
        prev_anchor = yesterday
    ctx = {
        'report_date': report_date,
        'report_period': report_period,
        'has_yesterday': DailyWorkReport.objects.filter(
            employee=request.user,
            report_date=prev_anchor,
            report_profile=report_profile or REPORT_PROFILE_OFFICE,
            report_period=report_period,
        ).exists(),
        'yesterday': prev_anchor,
        'can_view_team': can_view_team_reports(request.user) and get_team_report_members(request.user).exists(),
    }
    maybe_auto_sync()
    if report_profile:
        ctx.update(page_tools_context_for_profile(
            report_profile,
            report_period=report_period,
            user=request.user,
        ))
    return ctx


def _daily_report_defaults(report_profile: str, report_period: str = PERIOD_DAY):
    return {
        'shift': '',
        'report_profile': report_profile,
        'report_period': report_period,
        'status': DailyWorkReport.STATUS_DRAFT,
    }


def _load_daily_report(
    user,
    report_date,
    *,
    report_profile: str,
    report_period: str = PERIOD_DAY,
    shift: str = '',
):
    """Chỉ lấy bản ghi đã lưu; loại báo cáo theo trang SX/VP, không theo phòng ban."""
    if report_profile == REPORT_PROFILE_PRODUCTION and shift:
        from reports.production_slots import normalize_shift

        shift = normalize_shift(shift)
        base_qs = DailyWorkReport.objects.filter(
            employee=user,
            report_date=report_date,
            report_profile=report_profile,
            report_period=report_period,
        )
        report = base_qs.filter(shift=shift).first()
        if not report and shift == DailyWorkReport.SHIFT_MORNING:
            report = base_qs.filter(shift=DailyWorkReport.SHIFT_OVERTIME).first()
        if report:
            return report
        defaults = _daily_report_defaults(report_profile, report_period)
        defaults['shift'] = shift
        return DailyWorkReport(
            employee=user,
            report_date=report_date,
            **defaults,
        )

    try:
        return DailyWorkReport.objects.get(
            employee=user,
            report_date=report_date,
            report_profile=report_profile,
            report_period=report_period,
            shift=shift,
        )
    except DailyWorkReport.DoesNotExist:
        defaults = _daily_report_defaults(report_profile, report_period)
        if report_profile == REPORT_PROFILE_PRODUCTION and shift:
            defaults['shift'] = shift
        return DailyWorkReport(
            employee=user,
            report_date=report_date,
            **defaults,
        )


def _ensure_daily_report_saved(report):
    if report.pk:
        return report
    report.save()
    return report


def _finalize_report_submission(report, action):
    now = timezone.now()
    if action == 'submit':
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submitted_at = now
        return 'Đã gửi báo cáo.'
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = now
    return 'Đã lưu nháp báo cáo.'


def _ckeditor_context():
    lts_key = getattr(settings, 'CKEDITOR_LTS_LICENSE_KEY', '')
    return {
        'ckeditor_lts_license': lts_key,
        'ckeditor_use_lts': bool(lts_key),
        'reports_ck_upload_url': reverse('reports:ckeditor5_upload'),
    }


def _parse_week_start(request):
    raw = request.GET.get('week') or request.POST.get('week_start')
    return parse_week_start(raw)


def _load_weekly_report(user, week_start, *, report_profile: str):
    try:
        return WeeklyWorkReport.objects.get(employee=user, week_start=week_start)
    except WeeklyWorkReport.DoesNotExist:
        return WeeklyWorkReport(
            employee=user,
            week_start=week_start,
            report_profile=report_profile,
        )


def _ensure_weekly_report_saved(report):
    if report.pk:
        return report
    report.save()
    return report


def _weekly_attachments(report):
    if not report.pk:
        return [], []
    qs = report.attachments.all()
    images = [att for att in qs if att.is_image]
    files = [att for att in qs if not att.is_image]
    return images, files


def _report_comments_queryset(report):
    return report.comments.select_related('author', 'author__profile').prefetch_related('attachments')


def _handle_add_report_comment(request, *, report, can_review, redirect_fn, daily_report=None, weekly_report=None):
    from reports.comment_uploads import save_comment_attachments

    body = (request.POST.get('comment_body') or '').strip()
    uploaded_files = [f for f in request.FILES.getlist('comment_files') if f]
    if not body and not uploaded_files:
        messages.warning(request, 'Nhập nội dung hoặc chọn file đính kèm.')
        return redirect_fn()

    create_kwargs = {'author': request.user, 'body': body}
    if daily_report is not None:
        create_kwargs['daily_report'] = daily_report
    else:
        create_kwargs['weekly_report'] = weekly_report
    comment = ReportComment.objects.create(**create_kwargs)
    try:
        save_comment_attachments(comment, uploaded_files)
    except OSError as exc:
        logger.exception('Comment attachment save failed: %s', exc)
        mark_storage_unavailable()
        if not body:
            comment.delete()
            return redirect_fn()

    if can_review and report.status == report.STATUS_SUBMITTED and not report.hod_reviewed:
        if not (daily_report is not None and daily_report.is_production_report):
            report.hod_reviewed = True
            report.save(update_fields=['hod_reviewed', 'updated_at'])
    messages.success(request, 'Đã gửi nhận xét.')
    return redirect_fn()


def _comment_attachment_report(att):
    comment = att.comment
    if comment.daily_report_id:
        return comment.daily_report, 'daily'
    return comment.weekly_report, 'weekly'


def _can_view_comment_attachment(user, att) -> bool:
    report, kind = _comment_attachment_report(att)
    if kind == 'daily':
        if not can_view_user_report(user, report):
            return False
        return daily_report_visible_to_team(report) or report.employee_id == user.id
    if not can_view_user_weekly_report(user, report):
        return False
    return weekly_report_visible_to_team(report) or report.employee_id == user.id


def _delete_weekly_attachments(report, attachment_ids):
    if not attachment_ids:
        return 0
    qs = report.attachments.filter(pk__in=attachment_ids)
    count = qs.count()
    for att in qs:
        att.file.delete(save=False)
    qs.delete()
    return count


def _daily_report_attachments(report):
    """Gộp mọi file/ảnh đính kèm (kể cả dữ liệu cũ theo tab Bảng/Văn bản)."""
    images, files = [], []
    if not report.pk:
        return images, files
    for att in report.attachments.all():
        if att.is_image:
            images.append(att)
        else:
            files.append(att)
    return images, files


def _daily_attachments_by_tab(report):
    empty = ([], [])
    if not report.pk:
        return {'bang': empty, 'vanban': empty, 'link': empty}
    bang_images, bang_files = [], []
    vanban_images, vanban_files = [], []
    link_images, link_files = [], []
    for att in report.attachments.all():
        if att.source_tab == DailyWorkReportAttachment.SOURCE_BANG:
            if att.is_image:
                bang_images.append(att)
            else:
                bang_files.append(att)
        elif att.source_tab == DailyWorkReportAttachment.SOURCE_VANBAN:
            if att.is_image:
                vanban_images.append(att)
            else:
                vanban_files.append(att)
        elif att.source_tab == DailyWorkReportAttachment.SOURCE_LINK:
            if att.is_image:
                link_images.append(att)
            else:
                link_files.append(att)
    return {
        'bang': (bang_images, bang_files),
        'vanban': (vanban_images, vanban_files),
        'link': (link_images, link_files),
    }


def _delete_daily_attachments(report, attachment_ids):
    if not attachment_ids:
        return 0
    qs = report.attachments.filter(pk__in=attachment_ids)
    count = qs.count()
    for att in qs:
        att.file.delete(save=False)
    qs.delete()
    return count


def _weekly_context_common(request, week_start, *, report_profile: str):
    prev_week = week_start - timedelta(days=7)
    ctx = page_tools_context_for_profile(
        report_profile,
        report_period='weekly',
        user=request.user,
    )
    ctx.update({
        'week_start': week_start,
        'week_end': week_end(week_start),
        'week_label': week_label(week_start),
        'has_prev_week': WeeklyWorkReport.objects.filter(
            employee=request.user,
            week_start=prev_week,
            report_profile=report_profile,
        ).exists(),
        'prev_week': prev_week,
        'can_view_team': can_view_team_reports(request.user) and get_team_report_members(request.user).exists(),
        'reports_scope_label': report_profile_label(report_profile),
        'weekly_detail_url_name': weekly_detail_url_name_for_profile(report_profile),
    })
    maybe_auto_sync()
    return ctx


def _today_production_report(request, report_date):
    from reports.views_production_hourly import today_production_hourly

    def _production_context(req, d):
        return _report_context_common(req, d, report_profile=REPORT_PROFILE_PRODUCTION)

    return today_production_hourly(request, report_date, _production_context)


def _parse_proxy_rows(request, shift):
    from reports.production_slots import slot_count_for_shift

    count = slot_count_for_shift(shift)
    rows = []
    for i in range(count):
        rows.append({
            'slot_index': i,
            'product_code': request.POST.get(f'code_{i}', ''),
            'process_name': request.POST.get(f'process_{i}', ''),
            'quantity': request.POST.get(f'qty_{i}', ''),
            'norm_per_hour': request.POST.get(f'norm_{i}', ''),
            'damaged_quantity': request.POST.get(f'damaged_{i}', ''),
            'note': request.POST.get(f'note_{i}', ''),
        })
    return rows


@_reports_access_required
def proxy_report_entry(request):
    """Nhập hộ báo cáo sản xuất cho công nhân (tổ trưởng/QC) — 3 tab ca, bảng theo khung giờ."""
    from reports.production_hourly import (
        build_proxy_shift_sessions,
        can_edit_production_norms,
        can_manager_edit_unsubmitted_production_report,
        can_proxy_enter_daily_report,
        employee_self_submitted_production_report,
        report_has_manager_fixable_anomaly,
        save_proxy_shift_sessions,
    )
    from reports.production_shift_policy import shift_display_label
    import json

    if not can_view_team_reports(request.user):
        messages.error(request, 'Bạn không có quyền nhập hộ báo cáo.')
        return redirect('home_portal')

    report_date = _parse_report_date(request)

    team_members = list(
        get_team_report_members(request.user)
        .filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)
        .select_related('profile')
        .order_by('profile__full_name', 'username')
    )

    def _proxy_url(subject_id, shift=''):
        url = f"{reverse('reports:proxy_cn')}?date={report_date.isoformat()}&for_user={subject_id}"
        if shift:
            url += f'&shift={shift}'
        return url

    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    subject = None
    if for_user_id:
        try:
            subject = get_team_report_members(request.user).get(pk=int(for_user_id))
        except (ValueError, TypeError, User.DoesNotExist):
            subject = None
    if subject is None and team_members:
        subject = team_members[0]
    if subject is None:
        messages.info(request, 'Không có công nhân sản xuất cấp dưới để nhập hộ.')
        return redirect('reports:team_cn')
    if not can_proxy_enter_daily_report(request.user, subject):
        messages.error(request, 'Bạn không có quyền nhập hộ cho nhân viên này.')
        return redirect('reports:team_cn')

    subject_profile = getattr(subject, 'profile', None)
    subject_name = (subject_profile.full_name if subject_profile and subject_profile.full_name else subject.username)

    SHIFTS = [
        (DailyWorkReport.SHIFT_MORNING, 'Ca sáng'),
        (DailyWorkReport.SHIFT_NIGHT, 'Ca tối'),
    ]
    valid_shifts = {s for s, _ in SHIFTS}

    if request.method == 'POST':
        post_shift = (request.POST.get('shift') or '').strip().upper()
        from reports.production_slots import normalize_shift
        post_shift = normalize_shift(post_shift) if post_shift else ''
        if post_shift not in valid_shifts:
            messages.error(request, 'Ca làm không hợp lệ.')
            return redirect(_proxy_url(subject.id))
        report = _load_daily_report(
            subject, report_date,
            report_profile=REPORT_PROFILE_PRODUCTION, shift=post_shift,
        )
        report = _ensure_daily_report_saved(report)
        lock_session_times = employee_self_submitted_production_report(report)
        preserve_draft = (
            not lock_session_times
            and report.status != DailyWorkReport.STATUS_SUBMITTED
            and can_manager_edit_unsubmitted_production_report(request.user, report)
        )
        if lock_session_times:
            if not can_edit_production_norms(request.user, report):
                messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
                return redirect(_proxy_url(subject.id, post_shift))
        elif report.status != DailyWorkReport.STATUS_SUBMITTED:
            if not can_manager_edit_unsubmitted_production_report(request.user, report):
                messages.error(
                    request,
                    'Báo cáo chưa nộp chỉ được chỉnh sửa khi có công đoạn hiệu suất >200%, ≤0% '
                    'hoặc thời gian công đoạn 0 phút.',
                )
                return redirect(_proxy_url(subject.id, post_shift))
        elif is_report_locked(report) or is_report_edit_expired(report):
            messages.error(request, report_edit_denied_message(report))
            return redirect(_proxy_url(subject.id, post_shift))
        try:
            sessions = json.loads(request.POST.get('sessions_json') or '[]')
        except (ValueError, TypeError):
            sessions = []
        if not isinstance(sessions, list):
            sessions = []
        can_edit_declared_work_hours = not (
            is_report_locked(report) or is_report_edit_expired(report)
        )
        if lock_session_times:
            pass
        elif can_edit_declared_work_hours:
            from reports.production_hourly import resolve_declared_work_hours_for_save

            work_hours, work_hours_err = resolve_declared_work_hours_for_save(
                report,
                request.POST.get('declared_work_hours'),
                allow_keep_existing=True,
            )
            if work_hours_err:
                messages.error(request, work_hours_err)
                return redirect(_proxy_url(subject.id, post_shift))
            report.declared_work_hours = work_hours
        try:
            result = save_proxy_shift_sessions(
                report,
                sessions,
                request.user,
                content_edit_only=lock_session_times,
                preserve_draft=preserve_draft,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_proxy_url(subject.id, post_shift))
        if not result.get('sessions') and sessions:
            messages.warning(
                request,
                'Không có công đoạn nào được lưu — kiểm tra mã hàng, sản lượng và khung giờ.',
            )
            return redirect(_proxy_url(subject.id, post_shift))
        messages.success(
            request,
            f'Đã lưu chỉnh sửa {shift_display_label(post_shift)} cho {subject_name}.'
            if preserve_draft
            else f'Đã lưu {shift_display_label(post_shift)} cho {subject_name}.',
        )
        return redirect(_proxy_url(subject.id, post_shift))

    active_shift = (request.GET.get('shift') or DailyWorkReport.SHIFT_MORNING).strip().upper()
    if active_shift not in valid_shifts:
        active_shift = DailyWorkReport.SHIFT_MORNING

    from_detail_pk = None
    raw_from_detail = request.GET.get('from_detail') or request.POST.get('from_detail')
    if raw_from_detail and str(raw_from_detail).isdigit():
        from_detail_pk = int(raw_from_detail)

    tabs = []
    for shift, label in SHIFTS:
        report = _load_daily_report(
            subject, report_date,
            report_profile=REPORT_PROFILE_PRODUCTION, shift=shift,
        )
        lock_session_times = employee_self_submitted_production_report(report)
        can_edit_declared_work_hours = not (
            is_report_locked(report) or is_report_edit_expired(report)
        )
        show_declared_work_hours = True
        tabs.append({
            'shift': shift,
            'label': label,
            'data': build_proxy_shift_sessions(report),
            'is_submitted': bool(report.pk) and report.status == DailyWorkReport.STATUS_SUBMITTED,
            'is_locked': bool(report.pk) and (is_report_locked(report) or is_report_edit_expired(report)),
            'proxy_entered_by': report.proxy_entered_by if report.pk else None,
            'lock_session_times': lock_session_times,
            'declared_work_hours': report.declared_work_hours if report.pk else None,
            'show_declared_work_hours': show_declared_work_hours and not lock_session_times,
            'can_edit_declared_work_hours': can_edit_declared_work_hours,
            'report_id': report.pk if report.pk else None,
            'detail_url': (
                reverse('reports:detail_cn', kwargs={'pk': report.pk})
                if report.pk else ''
            ),
            'has_anomaly': (
                bool(report.pk)
                and report.status != DailyWorkReport.STATUS_SUBMITTED
                and report_has_manager_fixable_anomaly(report)
            ),
            'can_manager_edit': (
                lock_session_times
                or not report.pk
                or (
                    bool(report.pk)
                    and report.status == DailyWorkReport.STATUS_SUBMITTED
                    and not (is_report_locked(report) or is_report_edit_expired(report))
                )
                or (
                    report.status != DailyWorkReport.STATUS_SUBMITTED
                    and report_has_manager_fixable_anomaly(report)
                )
            ),
        })

    submitted_tabs = [tab for tab in tabs if tab['is_submitted']]
    anomaly_tabs = [tab for tab in tabs if tab.get('has_anomaly')]
    active_shift_tab = next((tab for tab in tabs if tab['shift'] == active_shift), None)
    from_detail_report = None
    if from_detail_pk:
        from_detail_report = DailyWorkReport.objects.filter(pk=from_detail_pk).first()

    if (
        from_detail_report
        and from_detail_report.status != DailyWorkReport.STATUS_SUBMITTED
        and report_has_manager_fixable_anomaly(from_detail_report)
    ):
        tabs = [tab for tab in tabs if tab['shift'] == from_detail_report.shift]
        edit_submitted_only = False
    elif active_shift_tab and active_shift_tab.get('has_anomaly') and not active_shift_tab['is_submitted']:
        tabs = [active_shift_tab]
        edit_submitted_only = False
    elif submitted_tabs:
        tabs = submitted_tabs
        edit_submitted_only = True
    elif anomaly_tabs:
        tabs = anomaly_tabs
        edit_submitted_only = False
    else:
        edit_submitted_only = False

    visible_shifts = {tab['shift'] for tab in tabs}
    if active_shift not in visible_shifts and tabs:
        active_shift = tabs[0]['shift']

    active_report = _load_daily_report(
        subject, report_date,
        report_profile=REPORT_PROFILE_PRODUCTION, shift=active_shift,
    )
    if from_detail_pk:
        back_url = reverse('reports:detail_cn', kwargs={'pk': from_detail_pk})
    elif edit_submitted_only and active_report.pk:
        back_url = reverse('reports:detail_cn', kwargs={'pk': active_report.pk})
    else:
        back_url = reverse('reports:team_cn') + f'?date={report_date.isoformat()}'

    return render(request, 'reports/proxy_entry.html', {
        'report_date': report_date,
        'subject': subject,
        'subject_name': subject_name,
        'subject_code': subject_profile.employee_code if subject_profile and subject_profile.employee_code else '',
        'department_name': subject_profile.department.name if subject_profile and subject_profile.department_id else '',
        'team_members': team_members,
        'tabs': tabs,
        'active_shift': active_shift,
        'empty_session': {
            'code': '', 'process': '', 'norm': '', 'total': '', 'damaged': '', 'note': '',
            'start_time': '', 'end_time': '',
        },
        'back_team_url': back_url,
        'back_url': back_url,
        'edit_submitted_only': edit_submitted_only,
    })


def _today_office_report(request, report_date, *, report_period: str = PERIOD_DAY):
    from hrm.permissions import get_profile as load_profile
    user_profile = load_profile(request.user)

    report = _load_daily_report(
        request.user,
        report_date,
        report_profile=REPORT_PROFILE_OFFICE,
        report_period=report_period,
    )

    # Nếu ngày/kỳ này đã có báo cáo nộp + đã khóa hoặc hết hạn sửa → chuyển sang lịch sử BC VP
    if (
        request.method == 'GET'
        and report.pk
        and report.status == DailyWorkReport.STATUS_SUBMITTED
        and (is_report_locked(report) or is_report_edit_expired(report))
    ):
        return redirect(reverse('reports:my_vp'))

    can_submit = can_submit_daily_report(request.user)
    can_edit = can_edit_own_daily_report(request.user, report, can_submit=can_submit)
    is_locked = is_report_locked(report)
    is_edit_expired = is_report_edit_expired(report)
    show_edit_expired = is_edit_expired and bool(report.pk)
    period_params = period_query_param(report_period, report_date)
    redirect_qs = urlencode(period_params)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, report_edit_denied_message(report))
            return redirect(f'{reverse("reports:today_vp")}?{redirect_qs}')
        # Bỏ chức năng lưu nháp — mọi lần lưu đều là nộp báo cáo
        action = 'submit'
        report = _ensure_daily_report_saved(report)
        form = OfficeDailyWorkReportForm(request.POST, request.FILES, instance=report, report_period=report_period)
        delete_ids = [int(pk) for pk in request.POST.getlist('delete_attachments') if pk.isdigit()]
        if form.is_valid():
            _delete_daily_attachments(report, delete_ids)
            was_submitted = bool(report.pk and report.status == DailyWorkReport.STATUS_SUBMITTED)
            report = form.save(commit=False)
            report.report_profile = REPORT_PROFILE_OFFICE
            report.report_period = report_period
            report.report_date = anchor_date_for_period(
                form.cleaned_data.get('report_date') or report_date,
                report_period,
            )
            report.shift = ''
            messages.success(request, _finalize_report_submission(report, action))
            report.save()
            from reports.models import DailyWorkReportEditLog
            from reports.report_edit_log import log_report_edit

            log_report_edit(
                report,
                request.user,
                action=(
                    DailyWorkReportEditLog.ACTION_RESUBMIT
                    if was_submitted
                    else DailyWorkReportEditLog.ACTION_SUBMIT
                ),
                summary=(
                    'Cập nhật báo cáo văn phòng.'
                    if was_submitted
                    else 'Gửi báo cáo văn phòng.'
                ),
            )
            has_uploads = bool(
                request.FILES.getlist('link_images')
                or request.FILES.getlist('link_files'),
            )
            if has_uploads:
                try:
                    save_daily_uploads(
                        report,
                        link_images=request.FILES.getlist('link_images'),
                        link_files=request.FILES.getlist('link_files'),
                    )
                except OSError as exc:
                    logger.exception('Daily report attachment save failed: %s', exc)
                    mark_storage_unavailable()
            return redirect(
                f'{reverse("reports:today_vp")}?{urlencode(period_query_param(report_period, report.report_date))}',
            )
    else:
        form = OfficeDailyWorkReportForm(instance=report, report_period=report_period)

    attachment_images, attachment_files = _daily_report_attachments(report)
    ctx = _report_context_common(
        request,
        report_date,
        report_profile=REPORT_PROFILE_OFFICE,
        report_period=report_period,
    )
    ctx.update(_ckeditor_context())
    copy_label = 'Sao chép kỳ trước'
    if report_period == PERIOD_WEEK:
        copy_label = 'Sao chép tuần trước'
    elif report_period == PERIOD_MONTH:
        copy_label = 'Sao chép tháng trước'
    ctx.update({
        'form': form,
        'report': report,
        'attachment_images': attachment_images,
        'attachment_files': attachment_files,
        'employee_name': (user_profile.full_name if user_profile else '') or request.user.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'copy_url': reverse('reports:copy_prev_vp') + f'?{urlencode(period_params)}' if ctx['has_yesterday'] and can_edit else None,
        'copy_label': copy_label,
        'copy_confirm': f'Sao chép nội dung từ {copy_label.lower()}?',
        'can_edit': can_edit,
        'is_locked': is_locked,
        'is_edit_expired': is_edit_expired,
        'show_edit_expired': show_edit_expired,
        'last_editable_on': last_editable_date(report),
        'office_period': report_period,
        'period_date_label': period_date_label(report_period),
        'period_date_input_type': period_date_input_type(report_period),
        'period_date_input_value': period_date_input_value(report_period, report_date),
        'period_intro_title': period_intro_title(report_period),
        'period_query': period_params,
        'period_nav_date': period_nav_date(request, report_period, report_date),
    })
    return render(request, 'reports/today_office.html', ctx)


def _weekly_report(request, *, report_profile: str):
    from hrm.permissions import get_profile as load_profile

    week_start = _parse_week_start(request)
    user_profile = load_profile(request.user)
    report = _load_weekly_report(request.user, week_start, report_profile=report_profile)
    weekly_url_name = weekly_url_name_for_profile(report_profile)
    copy_prev_week_url_name = copy_prev_week_url_name_for_profile(report_profile)
    can_submit = can_submit_daily_report(request.user)
    can_edit = can_edit_own_weekly_report(request.user, report, can_submit=can_submit)
    is_locked = is_report_locked(report)
    is_edit_expired = is_report_edit_expired(report)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, report_edit_denied_message(report))
            return redirect(f'{reverse(weekly_url_name)}?week={week_start.isoformat()}')
        # Bỏ chức năng lưu nháp — mọi lần lưu đều là nộp báo cáo
        action = 'submit'
        report = _ensure_weekly_report_saved(report)
        form = WeeklyWorkReportForm(request.POST, instance=report)
        delete_ids = [int(pk) for pk in request.POST.getlist('delete_attachments') if pk.isdigit()]
        image_uploads = request.FILES.getlist('images')
        file_uploads = request.FILES.getlist('files')

        if form.is_valid():
            _delete_weekly_attachments(report, delete_ids)
            remaining = report.attachments.count()
            if action == 'submit' and not weekly_report_has_content(
                links_text=form.cleaned_data.get('links', ''),
                image_uploads=image_uploads,
                file_uploads=file_uploads,
                attachment_count=remaining,
            ):
                form.add_error(
                    None,
                    'Khi gửi báo cáo tuần, điền ít nhất một link hoặc tải lên file/ảnh.',
                )
            else:
                report = form.save(commit=False)
                report.report_profile = report_profile
                msg = _finalize_report_submission(report, action)
                messages.success(request, msg)
                report.save()
                if image_uploads or file_uploads:
                    try:
                        save_weekly_uploads(report, image_list=image_uploads, file_list=file_uploads)
                    except OSError as exc:
                        logger.exception('Weekly report attachment save failed: %s', exc)
                        mark_storage_unavailable()
                return redirect(f'{reverse(weekly_url_name)}?week={week_start.isoformat()}')
    else:
        form = WeeklyWorkReportForm(instance=report)

    images, files = _weekly_attachments(report)
    ctx = _weekly_context_common(request, week_start, report_profile=report_profile)
    ctx.update({
        'form': form,
        'report': report,
        'weekly_images': images,
        'weekly_files': files,
        'employee_name': (user_profile.full_name if user_profile else '') or request.user.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'copy_url': reverse(copy_prev_week_url_name) if ctx['has_prev_week'] and can_edit else None,
        'copy_label': 'Sao chép tuần trước',
        'copy_confirm': 'Sao chép nội dung từ tuần trước?',
        'can_edit': can_edit,
        'is_locked': is_locked,
        'is_edit_expired': is_edit_expired,
        'last_editable_on': last_editable_date(report),
    })
    return render(request, 'reports/weekly.html', ctx)


@_require_submit_access
def weekly_report_cn(request):
    messages.info(request, 'Báo cáo tuần SX đã ngừng dùng — chỉ dùng báo cáo ngày SX.')
    return redirect('reports:today_cn')


@_require_submit_access
def weekly_report_vp(request):
    period = request.GET.get('period') or PERIOD_WEEK
    anchor = parse_period_anchor_date(request, period)
    return redirect(f'{reverse("reports:today_vp")}?{urlencode(period_query_param(period, anchor))}')


@_require_submit_access
def weekly_report_redirect(request):
    return redirect(weekly_url_for_user(request.user))


@_require_submit_access
def copy_prev_week(request, *, report_profile: str):
    this_week = monday_of(timezone.localdate())
    prev_week = this_week - timedelta(days=7)
    source = WeeklyWorkReport.objects.filter(
        employee=request.user,
        week_start=prev_week,
        report_profile=report_profile,
    ).first()
    weekly_url_name = weekly_url_name_for_profile(report_profile)
    if not source:
        messages.warning(request, 'Không có báo cáo tuần trước để sao chép.')
        return redirect(reverse(weekly_url_name))

    report, _ = WeeklyWorkReport.objects.get_or_create(
        employee=request.user,
        week_start=this_week,
        defaults={
            'status': WeeklyWorkReport.STATUS_DRAFT,
            'report_profile': report_profile,
        },
    )
    report.report_profile = report_profile
    report.status = WeeklyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    report.links = source.links
    report.save()
    _delete_weekly_attachments(report, list(report.attachments.values_list('pk', flat=True)))
    try:
        copy_weekly_attachments(source, report)
    except OSError as exc:
        logger.exception('Copy weekly attachments failed: %s', exc)
        mark_storage_unavailable()
    messages.success(request, 'Đã sao chép báo cáo tuần trước. Kiểm tra và gửi lại.')
    return redirect(f'{reverse(weekly_url_name)}?week={this_week.isoformat()}')


@_require_submit_access
def copy_prev_week_cn(request):
    return copy_prev_week(request, report_profile=REPORT_PROFILE_PRODUCTION)


@_require_submit_access
def copy_prev_week_vp(request):
    params = period_query_param(PERIOD_WEEK, monday_of(timezone.localdate()))
    query = request.META.get('QUERY_STRING', '').strip()
    if query:
        return redirect(f'{reverse("reports:copy_prev_vp")}?{query}')
    return redirect(f'{reverse("reports:copy_prev_vp")}?{urlencode(params)}')


@_require_submit_access
def copy_prev_week_redirect(request):
    return redirect(redirect_copy_prev_week_legacy(request.user))


def _resolve_today_subject(request):
    subject = request.user
    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    if for_user_id:
        try:
            subject = get_team_report_members(request.user).get(pk=int(for_user_id))
        except (ValueError, TypeError, User.DoesNotExist):
            subject = request.user
    return subject


@_require_today_report_access
def today_report(request):
    query = request.GET.urlencode()
    target = today_url_for_user(_resolve_today_subject(request))
    if query:
        target = f'{target}?{query}'
    return redirect(target)


@module_perm_required(MODULE_REPORTS, 'create')
@require_POST
def ckeditor5_upload(request):
    upload = request.FILES.get('upload') or request.FILES.get('file')
    if not upload:
        return _ckeditor_upload_error('Không có file.')
    if not _is_allowed_ckeditor_image(upload):
        return _ckeditor_upload_error('File không hợp lệ.')
    if upload.size > _CK5_MAX_BYTES:
        return _ckeditor_upload_error('Ảnh quá lớn (tối đa 5MB).')

    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext not in _CK5_IMAGE_EXTS:
        content_type = (upload.content_type or '').split(';')[0].strip().lower()
        ext = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/pjpeg': '.jpg',
            'image/png': '.png',
            'image/x-png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp',
            'image/x-ms-bmp': '.bmp',
        }.get(content_type, '.png')
    try:
        rel_path = save_inline_image(
            upload,
            username=request.user.username,
            report_date=parse_upload_report_date(request),
            ext=ext,
            period=parse_office_period(request),
        )
    except OSError as exc:
        logger.exception('CKEditor upload failed for %s: %s', request.user.username, exc)
        mark_storage_unavailable()
        return _ckeditor_upload_error('Không lưu được ảnh. Vui lòng thử lại.', status=503)
    url = request.build_absolute_uri(
        reverse('reports:inline_image', kwargs={'relpath': rel_path}),
    )
    return JsonResponse({
        'uploaded': 1,
        'fileName': os.path.basename(rel_path),
        'url': url,
    })


@_reports_access_required
@require_POST
def sync_nas_pending_now(request):
    """Nút bấm: đẩy file báo cáo lưu tạm trên VPS lên NAS rồi xóa bản tạm."""
    pending_before = count_pending_nas_sync()
    if not pending_before:
        messages.info(request, 'Không có file nào chờ đồng bộ lên NAS.')
        return _redirect_back(request)

    stats = sync_all_pending()
    remaining = count_pending_nas_sync()
    if stats.get('status') == 'nas_down':
        messages.warning(
            request,
            f'NAS chưa sẵn sàng. Đã đồng bộ {stats.get("synced", 0)} file, '
            f'còn {remaining} file chờ — thử lại sau khi NAS phục hồi.',
        )
    elif stats.get('synced'):
        messages.success(request, f'Đã đồng bộ {stats["synced"]} file lên NAS.')
    else:
        messages.info(request, 'Không có file nào được đồng bộ.')
    return _redirect_back(request)


def _redirect_back(request):
    nxt = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(nxt)
    return redirect('reports:hub')


@_require_submit_access
def copy_prev_vp(request):
    report_period = parse_office_period(request)
    anchor = parse_period_anchor_date(request, report_period)
    if report_period == PERIOD_MONTH:
        prev = first_day_of_month(anchor.replace(day=1) - timedelta(days=1))
    elif report_period == PERIOD_WEEK:
        prev = anchor - timedelta(days=7)
    else:
        prev = anchor - timedelta(days=1)

    source = DailyWorkReport.objects.filter(
        employee=request.user,
        report_date=prev,
        report_profile=REPORT_PROFILE_OFFICE,
        report_period=report_period,
    ).prefetch_related('attachments').first()
    if not source:
        messages.warning(request, 'Không có báo cáo kỳ trước để sao chép.')
        return redirect(f'{reverse("reports:today_vp")}?{urlencode(period_query_param(report_period, anchor))}')

    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=anchor,
        report_profile=REPORT_PROFILE_OFFICE,
        report_period=report_period,
        defaults=_daily_report_defaults(REPORT_PROFILE_OFFICE, report_period),
    )
    report.report_profile = REPORT_PROFILE_OFFICE
    report.report_period = report_period
    report.shift = ''
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    report.title = source.title
    report.spreadsheet_json = source.spreadsheet_json
    report.document_html = source.document_html
    report.links = source.links
    report.save()
    report.lines.all().delete()
    _delete_daily_attachments(report, list(report.attachments.values_list('pk', flat=True)))
    try:
        copy_daily_attachments(source, report)
    except OSError as exc:
        logger.exception('Copy daily attachments failed: %s', exc)
        mark_storage_unavailable()
    messages.success(request, 'Đã sao chép báo cáo kỳ trước. Kiểm tra và nộp lại.')
    return redirect(f'{reverse("reports:today_vp")}?{urlencode(period_query_param(report_period, anchor))}')


@_require_submit_access
def copy_yesterday(request, *, report_profile: str):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    source = DailyWorkReport.objects.filter(
        employee=request.user,
        report_date=yesterday,
        report_profile=report_profile,
        report_period=PERIOD_DAY,
        shift=DailyWorkReport.SHIFT_MORNING if report_profile == REPORT_PROFILE_PRODUCTION else '',
    ).prefetch_related('lines', 'attachments').first()
    if not source:
        messages.warning(request, 'Không có báo cáo hôm qua để sao chép.')
        return redirect(today_url_for_user(request.user))

    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=today,
        report_profile=report_profile,
        report_period=PERIOD_DAY,
        shift=DailyWorkReport.SHIFT_MORNING if report_profile == REPORT_PROFILE_PRODUCTION else '',
        defaults=_daily_report_defaults(report_profile, PERIOD_DAY),
    )
    report.report_profile = report_profile
    if report_profile == REPORT_PROFILE_PRODUCTION:
        report.shift = DailyWorkReport.SHIFT_MORNING
    else:
        report.shift = ''
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    if report_profile == REPORT_PROFILE_OFFICE:
        report.title = source.title
        report.spreadsheet_json = source.spreadsheet_json
        report.document_html = source.document_html
        report.links = source.links
        report.save()
        report.lines.all().delete()
        _delete_daily_attachments(report, list(report.attachments.values_list('pk', flat=True)))
        try:
            copy_daily_attachments(source, report)
        except OSError as exc:
            logger.exception('Copy daily attachments failed: %s', exc)
            mark_storage_unavailable()
    else:
        report.spreadsheet_json = None
        report.document_html = ''
        report.save()
        report.lines.all().delete()
        for idx, line in enumerate(source.lines.all()):
            report.lines.create(
                area=line.area,
                order_code=line.order_code,
                product_name=line.product_name,
                quantity=line.quantity,
                unit=line.unit,
                note=line.note,
                sort_order=idx,
            )
    messages.success(request, 'Đã sao chép báo cáo hôm qua. Kiểm tra và nộp lại.')
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return redirect(
            f'{reverse("reports:today_cn")}?date={today.isoformat()}&shift={DailyWorkReport.SHIFT_MORNING}'
        )
    return redirect(f'{reverse("reports:today_vp")}?date={today.isoformat()}')


def _my_reports_period(request, *, office: bool = False, production: bool = False):
    """Lịch sử SX/VP: không còn chia tab kỳ — luôn danh sách theo khoảng ngày."""
    if office or production:
        return 'daily'
    period = (request.GET.get('period') or 'daily').strip().lower()
    if period not in ('daily', 'weekly'):
        period = 'daily'
    return period


@_reports_access_required
def my_reports(request):
    url = my_url_for_user(request.user)
    query = request.META.get('QUERY_STRING', '').strip()
    if query:
        return redirect(f'{url}?{query}')
    return redirect(url)


@_reports_access_required
def my_reports_cn(request):
    return _my_reports(request, daily_report_profile=REPORT_PROFILE_PRODUCTION)


@_reports_access_required
def my_reports_vp(request):
    return _my_reports(request, daily_report_profile=REPORT_PROFILE_OFFICE)


def _my_reports(request, daily_report_profile=None):
    search_query = get_search_query(request)
    is_office = daily_report_profile == REPORT_PROFILE_OFFICE
    is_production = daily_report_profile == REPORT_PROFILE_PRODUCTION
    period = _my_reports_period(request, office=is_office, production=is_production)
    subject = request.user
    history_employee_name = ''
    for_user_id = request.GET.get('for_user')
    if for_user_id:
        try:
            subject = get_team_report_members(request.user).get(pk=int(for_user_id))
            profile = getattr(subject, 'profile', None)
            history_employee_name = profile.full_name if profile and profile.full_name else subject.username
        except (ValueError, TypeError, User.DoesNotExist):
            messages.error(request, 'Không tìm thấy nhân viên hoặc bạn không có quyền xem lịch sử.')
            return redirect('reports:hub')
    elif not can_submit_daily_report(request.user) and can_view_team_reports(request.user):
        from reports.navigation import team_pending_url_for_user
        return redirect(team_pending_url_for_user(request.user))
    elif not can_view_own_report_history(request.user, daily_report_profile):
        return redirect('home_portal')

    # Bộ lọc từ ngày — đến ngày (mặc định 1 tuần gần nhất)
    history_date_from = _parse_iso_date(request.GET.get('from'))
    history_date_to = _parse_iso_date(request.GET.get('to'))
    if not history_date_to:
        history_date_to = timezone.localdate()
    if not history_date_from:
        history_date_from = history_date_to - timedelta(days=6)

    if daily_report_profile in (REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION):
        logs_qs = DailyWorkReportEditLog.objects.filter(
            report__employee=subject,
            report__report_profile=daily_report_profile,
        ).select_related(
            'report',
            'edited_by',
            'edited_by__profile',
        )
        if history_date_from:
            logs_qs = logs_qs.filter(edited_at__date__gte=history_date_from)
        if history_date_to:
            logs_qs = logs_qs.filter(edited_at__date__lte=history_date_to)
        logs_qs = apply_combined_search(logs_qs, search_query, lambda term: (
            Q(summary__icontains=term)
            | Q(report__title__icontains=term)
            | Q(report__document_html__icontains=term)
            | Q(report__hod_note__icontains=term)
            | Q(edited_by__profile__full_name__icontains=term)
            | Q(edited_by__username__icontains=term)
        ))
        if daily_report_profile == REPORT_PROFILE_PRODUCTION:
            from reports.report_lock import auto_reject_expired_production_reports

            auto_reject_expired_production_reports(
                employee_ids=[subject.pk],
                date_from=history_date_from,
                date_to=history_date_to,
            )
        page_obj, query_string = paginate_queryset(
            request,
            logs_qs.order_by('-edited_at', '-id'),
        )
    else:
        if period == 'weekly':
            reports_qs = meaningful_weekly_reports_qs().filter(
                employee=subject,
            )
            if daily_report_profile:
                reports_qs = reports_qs.filter(report_profile=daily_report_profile)
            reports_qs = reports_qs.annotate(
                attachment_count=Count('attachments'),
                has_manager_comment=Exists(
                    ReportComment.objects.filter(weekly_report=OuterRef('pk')).exclude(author=subject),
                ),
                has_employee_reply=Exists(
                    ReportComment.objects.filter(weekly_report=OuterRef('pk'), author=subject),
                ),
            ).order_by('-week_start')
            reports_qs = apply_combined_search(reports_qs, search_query, lambda term: (
                Q(hod_note__icontains=term)
                | Q(status__icontains=term)
                | Q(links__icontains=term)
            ))
        else:
            reports_qs = DailyWorkReport.objects.filter(
                employee=subject,
                report_period=PERIOD_DAY,
            )
            if daily_report_profile:
                reports_qs = reports_qs.filter(report_profile=daily_report_profile)
            reports_qs = reports_qs.annotate(
                line_count=Count('lines'),
                total_qty=Sum('lines__quantity'),
                has_manager_comment=Exists(
                    ReportComment.objects.filter(daily_report=OuterRef('pk')).exclude(author=subject),
                ),
                has_employee_reply=Exists(
                    ReportComment.objects.filter(daily_report=OuterRef('pk'), author=subject),
                ),
            ).order_by('-report_date')
            reports_qs = apply_combined_search(reports_qs, search_query, lambda term: (
                Q(hod_note__icontains=term)
                | Q(status__icontains=term)
                | Q(lines__area__icontains=term)
                | Q(lines__order_code__icontains=term)
                | Q(lines__product_name__icontains=term)
            ))

        if history_date_from:
            if period == 'weekly':
                reports_qs = reports_qs.filter(week_start__gte=history_date_from)
            else:
                reports_qs = reports_qs.filter(report_date__gte=history_date_from)
        if history_date_to:
            if period == 'weekly':
                reports_qs = reports_qs.filter(week_start__lte=history_date_to)
            else:
                reports_qs = reports_qs.filter(report_date__lte=history_date_to)

        page_obj, query_string = paginate_queryset(request, reports_qs)

    scope_label = 'SX' if daily_report_profile == REPORT_PROFILE_PRODUCTION else 'VP' if daily_report_profile else ''
    is_edit_history = daily_report_profile in (REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION)
    ctx = {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_view_team': can_view_team_reports(request.user) and get_team_report_members(request.user).exists(),
        'report_period': period,
        'history_employee_name': history_employee_name,
        'history_for_user_id': subject.pk if subject.pk != request.user.pk else None,
        'reports_scope_label': scope_label,
        'today_url_name': (
            'reports:today_cn'
            if daily_report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:today_vp'
        ),
        'my_url_name': my_url_name_for_profile(daily_report_profile) if daily_report_profile else 'reports:my',
        'team_url_name': team_url_name_for_profile(daily_report_profile) if daily_report_profile else 'reports:team_cn',
        'team_weekly_url_name': (
            team_weekly_url_name_for_profile(daily_report_profile)
            if daily_report_profile else 'reports:team_weekly_cn'
        ),
        'weekly_url_name': (
            weekly_url_name_for_profile(daily_report_profile)
            if daily_report_profile else 'reports:weekly_cn'
        ),
        'weekly_detail_url_name': (
            weekly_detail_url_name_for_profile(daily_report_profile)
            if daily_report_profile else 'reports:weekly_detail_cn'
        ),
        'is_office_history': is_office,
        'is_edit_history': is_edit_history,
        'history_date_from': history_date_from,
        'history_date_to': history_date_to,
    }
    if is_edit_history:
        ctx['edit_logs'] = page_obj.object_list
    else:
        ctx['reports'] = page_obj.object_list
        ctx['detail_url_name'] = (
            'reports:detail_cn'
            if daily_report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:detail_vp'
        )
    return render(request, 'reports/my_reports.html', ctx)


def _team_queryset(viewer, search_query, *, report_profile: str | None = None):
    team = get_team_report_members(viewer).select_related(
        'profile',
        'profile__department',
        'profile__division',
    ).order_by('profile__department__sort_order', 'profile__full_name', 'username')
    if report_profile:
        team = filter_team_members_for_report_profile(team, report_profile)
    return apply_user_search(team, search_query)


def _build_department_group_rows(viewer, team, report_map, visible_fn, dept_filter=''):
    all_groups = build_report_team_department_groups(viewer, team)
    dept_choices = department_filter_choices(all_groups)
    groups = (
        build_report_team_department_groups(viewer, team, dept_filter=dept_filter)
        if dept_filter else all_groups
    )
    department_groups = []
    for group in groups:
        rows = []
        for member in group['members']:
            report = report_map.get(member.id)
            rows.append({
                'member': member,
                'report': report if visible_fn(report) else None,
            })
        department_groups.append({**group, 'rows': rows})
    return department_groups, dept_choices


TEAM_STATUS_SUBMITTED = 'submitted'
TEAM_STATUS_MISSING = 'missing'
TEAM_STATUS_NO_REPORT = 'no_report'
TEAM_STATUS_REVIEWED = 'reviewed'
TEAM_STATUS_NOT_REVIEWED = 'not_reviewed'
TEAM_STATUS_REJECTED = 'rejected'
TEAM_SUMMARY_DEFAULT_SPAN_DAYS = 7


def _summary_week_date_range(anchor_to=None):
    """Khoảng mặc định trang tổng hợp SX — 1 tuần (7 ngày) tính đến anchor_to."""
    anchor_to = anchor_to or timezone.localdate()
    anchor_from = anchor_to - timedelta(days=TEAM_SUMMARY_DEFAULT_SPAN_DAYS - 1)
    return anchor_from, anchor_to


def _summary_list_query_params(*, dept_filter: str = '') -> dict[str, str]:
    date_from, date_to = _summary_week_date_range()
    params = team_date_range_query_params(date_from, date_to)
    params['shift'] = DailyWorkReport.SHIFT_MORNING
    if dept_filter:
        params['dept'] = dept_filter
    return params


def _parse_team_summary_shift(request) -> str:
    from reports.production_slots import normalize_shift

    raw = (request.GET.get('shift') or DailyWorkReport.SHIFT_MORNING).strip().upper()
    shift = normalize_shift(raw)
    if shift not in PRODUCTION_SHIFT_ORDER:
        return DailyWorkReport.SHIFT_MORNING
    return shift


def _parse_team_status_filter(request) -> str:
    val = (request.GET.get('status') or '').strip().lower()
    if val in (
        TEAM_STATUS_SUBMITTED,
        TEAM_STATUS_MISSING,
        TEAM_STATUS_NO_REPORT,
        TEAM_STATUS_REVIEWED,
        TEAM_STATUS_NOT_REVIEWED,
        TEAM_STATUS_REJECTED,
    ):
        return val
    return ''


def _team_row_is_submitted(row, *, submitted_status: str) -> bool:
    report = row.get('report')
    return bool(report and report.status == submitted_status)


def _office_team_row_matches_filter(row, status_filter: str, *, submitted_status: str) -> bool:
    """Lọc ô thống kê VP: đã nộp / chưa nộp / chưa xem / đã xem."""
    report = row.get('report')
    is_submitted = bool(report and report.status == submitted_status)
    if status_filter == TEAM_STATUS_SUBMITTED:
        return is_submitted
    if status_filter == TEAM_STATUS_MISSING:
        return not is_submitted
    if status_filter == TEAM_STATUS_REVIEWED:
        return bool(report and report.hod_reviewed)
    if status_filter == TEAM_STATUS_NOT_REVIEWED:
        return bool(is_submitted and report and not report.hod_reviewed)
    return True


def _office_team_view_row_counts(department_groups) -> dict:
    """Đếm đã xem / chưa xem trên danh sách VP (trước khi lọc status)."""
    reviewed = 0
    not_reviewed = 0
    for group in department_groups:
        for row in group.get('rows') or []:
            report = row.get('report')
            if not report or report.status != DailyWorkReport.STATUS_SUBMITTED:
                continue
            if report.hod_reviewed:
                reviewed += 1
            else:
                not_reviewed += 1
    return {'reviewed': reviewed, 'not_reviewed': not_reviewed}


def _filter_team_department_groups(
    department_groups,
    status_filter: str,
    *,
    submitted_status: str,
    row_is_submitted=None,
    row_matches_filter=None,
):
    if not status_filter:
        return department_groups
    is_submitted = row_is_submitted or _team_row_is_submitted
    filtered = []
    for group in department_groups:
        rows = []
        for row in group['rows']:
            if row_matches_filter:
                include = row_matches_filter(
                    row, status_filter, submitted_status=submitted_status,
                )
            elif status_filter == TEAM_STATUS_SUBMITTED:
                include = is_submitted(row, submitted_status=submitted_status)
            elif status_filter == TEAM_STATUS_MISSING:
                include = not is_submitted(row, submitted_status=submitted_status)
            else:
                include = False
            if include:
                rows.append(row)
        if rows:
            filtered.append({**group, 'rows': rows})
    return filtered


def _production_team_row_is_submitted(row, *, submitted_status: str):
    return production_team_row_is_submitted(row, submitted_status=submitted_status)


def _team_stat_urls(base_params: dict) -> dict:
    def _url(extra: dict) -> str:
        params = {**base_params, **extra}
        params = {k: v for k, v in params.items() if v not in (None, '')}
        return '?' + urlencode(params)

    return {
        # 'all' phải xóa status (base_params có thể đang mang status hiện tại)
        'all': _url({'status': ''}),
        'submitted': _url({'status': TEAM_STATUS_SUBMITTED}),
        'missing': _url({'status': TEAM_STATUS_MISSING}),
        'no_report': _url({'status': TEAM_STATUS_NO_REPORT}),
        'reviewed': _url({'status': TEAM_STATUS_REVIEWED}),
        'not_reviewed': _url({'status': TEAM_STATUS_NOT_REVIEWED}),
        'rejected': _url({'status': TEAM_STATUS_REJECTED}),
    }


@_reports_access_required
def team_reports(request):
    return redirect(redirect_team_legacy(request.user))


@_reports_access_required
def team_reports_cn(request):
    return _team_reports_for_profile(request, REPORT_PROFILE_PRODUCTION)


@_reports_access_required
def team_reports_vp(request):
    return _team_reports_for_profile(request, REPORT_PROFILE_OFFICE)


@_reports_access_required
def team_summary_cn(request):
    """Báo cáo tổng hợp SX — ma trận hiệu suất trung bình NV × ngày."""
    from .production_team import build_production_team_summary

    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        return redirect('home_portal')

    date_from, date_to = parse_team_date_range(request, default_span_days=TEAM_SUMMARY_DEFAULT_SPAN_DAYS)
    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    division_filter = (request.GET.get('division') or '').strip()
    shift_filter = _parse_team_summary_shift(request)

    from hrm.user_search import filter_users_by_division

    team_base = _team_queryset(request.user, search_query, report_profile=REPORT_PROFILE_PRODUCTION)
    division_choices = division_filter_choices_from_team(
        request.user,
        team_base,
        dept_filter=dept_filter,
    )
    team = (
        filter_users_by_division(team_base, division_filter)
        if division_filter else team_base
    )
    all_team_ids = list(team.values_list('id', flat=True))
    team_count = team.count()

    reports = query_production_team_reports(all_team_ids, date_from, date_to)
    reports_by_employee = build_production_reports_by_employee(reports)
    summary = build_production_team_summary(
        request.user,
        team,
        reports_by_employee,
        daily_report_visible_to_team,
        date_from=date_from,
        date_to=date_to,
        dept_filter=dept_filter,
        shift_filter=shift_filter,
    )

    base_params = team_date_range_query_params(date_from, date_to)
    base_params['shift'] = shift_filter
    if search_query:
        base_params['q'] = search_query
    if dept_filter:
        base_params['dept'] = dept_filter
    if division_filter:
        base_params['division'] = division_filter

    tab_params = {k: v for k, v in base_params.items() if k != 'shift'}

    return render(request, 'reports/team_summary.html', {
        'summary': summary,
        'days': summary['days'],
        'department_groups': summary['groups'],
        'dept_choices': summary['dept_choices'],
        'division_choices': division_choices,
        'selected_dept': dept_filter,
        'selected_division': division_filter,
        'search_query': search_query,
        'range_from': date_from,
        'range_to': date_to,
        'report_date': date_to,
        'team_count': team_count,
        'active_shift': shift_filter,
        'shift_tabs': build_production_summary_shift_tabs(
            active_shift=shift_filter,
            base_params=tab_params,
        ),
        'team_page_title': 'Báo cáo tổng hợp (SX)',
        'reports_scope_label': 'SX',
        'can_submit_report': can_submit_daily_report(request.user),
        'today_url_name': 'reports:today_cn',
        'team_url_name': 'reports:team_cn',
        'team_list_query': urlencode(base_params),
    })


@_reports_access_required
def team_summary_cn_export(request):
    """Xuất Excel báo cáo tổng hợp SX (theo bộ lọc hiện tại)."""
    from .production_team import build_production_team_summary
    from .excel_export import export_production_team_summary_xlsx

    if not can_view_team_reports(request.user):
        return redirect('home_portal')

    date_from, date_to = parse_team_date_range(request, default_span_days=TEAM_SUMMARY_DEFAULT_SPAN_DAYS)
    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    division_filter = (request.GET.get('division') or '').strip()
    shift_filter = _parse_team_summary_shift(request)

    from hrm.user_search import filter_users_by_division

    team_base = _team_queryset(request.user, search_query, report_profile=REPORT_PROFILE_PRODUCTION)
    team = (
        filter_users_by_division(team_base, division_filter)
        if division_filter else team_base
    )
    all_team_ids = list(team.values_list('id', flat=True))
    reports = query_production_team_reports(all_team_ids, date_from, date_to)
    reports_by_employee = build_production_reports_by_employee(reports)
    summary = build_production_team_summary(
        request.user,
        team,
        reports_by_employee,
        daily_report_visible_to_team,
        date_from=date_from,
        date_to=date_to,
        dept_filter=dept_filter,
        shift_filter=shift_filter,
    )
    return export_production_team_summary_xlsx(
        summary,
        date_from=date_from,
        date_to=date_to,
        shift_label=summary['shift_label'],
    )


def _team_reports_for_profile(request, report_profile: str, *, report_period: str = PERIOD_DAY):
    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        if can_submit_daily_report(request.user):
            return redirect(today_url_for_user(request.user))
        return redirect('home_portal')

    date_from, date_to = parse_team_date_range(
        request,
        default_span_days=TEAM_MANAGEMENT_DEFAULT_SPAN_DAYS,
    )
    report_date = date_to
    if report_profile == REPORT_PROFILE_OFFICE:
        period_filter = parse_team_period_filter(request)
        report_period = period_filter or PERIOD_DAY
    else:
        period_filter = ''
        report_period = PERIOD_DAY

    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    division_filter = (request.GET.get('division') or '').strip()
    status_filter = _parse_team_status_filter(request)
    team_base = _team_queryset(request.user, search_query, report_profile=report_profile)
    division_choices = division_filter_choices_from_team(
        request.user,
        team_base,
        dept_filter=dept_filter,
    )
    team = (
        filter_users_by_division(team_base, division_filter)
        if division_filter else team_base
    )
    all_team_ids = list(team.values_list('id', flat=True))
    team_count = team.count()

    if report_profile == REPORT_PROFILE_OFFICE:
        reports_in_range = query_team_office_reports_in_range(
            all_team_ids,
            date_from,
            date_to,
            period_filter,
        )
        department_groups, dept_choices, submitted_employee_ids = build_vp_team_department_groups(
            request.user,
            team,
            reports_in_range,
            daily_report_visible_to_team,
            dept_filter=dept_filter,
        )
        submitted = len(submitted_employee_ids)
        missing = team_count - submitted
        no_report_count = 0
        view_counts = _office_team_view_row_counts(department_groups)
        reviewed_count = view_counts['reviewed']
        not_reviewed_count = view_counts['not_reviewed']
        rejected_count = 0
    else:
        from reports.report_lock import auto_reject_expired_production_reports

        auto_reject_expired_production_reports(
            employee_ids=all_team_ids,
            date_from=date_from,
            date_to=date_to,
        )
        reports = query_production_team_reports(all_team_ids, date_from, date_to)
        reports_by_employee = build_production_reports_by_employee(reports)
        status_counts = production_team_status_counts(
            all_team_ids,
            reports_by_employee,
            daily_report_visible_to_team,
        )
        submitted = status_counts['submitted']
        missing = status_counts['unsubmitted_report']
        no_report_count = status_counts['no_report']
        department_groups, dept_choices = build_production_team_department_groups(
            request.user,
            team,
            reports_by_employee,
            daily_report_visible_to_team,
            date_from=date_from,
            date_to=date_to,
            dept_filter=dept_filter,
        )
        review_counts = production_team_review_row_counts(department_groups)
        reviewed_count = review_counts['reviewed']
        not_reviewed_count = review_counts['not_reviewed']
        rejected_count = review_counts['rejected']

    department_groups = _filter_team_department_groups(
        department_groups,
        status_filter,
        submitted_status=DailyWorkReport.STATUS_SUBMITTED,
        row_is_submitted=(
            _production_team_row_is_submitted
            if report_profile == REPORT_PROFILE_PRODUCTION
            else None
        ),
        row_matches_filter=(
            production_team_row_matches_filter
            if report_profile == REPORT_PROFILE_PRODUCTION
            else _office_team_row_matches_filter
        ),
    )

    sort_key, sort_dir = resolve_team_sort(request.GET.get('sort'), request.GET.get('dir'))
    department_groups = sort_team_department_groups(department_groups, sort_key, sort_dir)

    if report_profile == REPORT_PROFILE_OFFICE:
        base_params = team_date_range_query_params(date_from, date_to, period=period_filter)
    else:
        base_params = team_date_range_query_params(date_from, date_to)
    if search_query:
        base_params['q'] = search_query
    if dept_filter:
        base_params['dept'] = dept_filter
    if division_filter:
        base_params['division'] = division_filter
    if status_filter:
        base_params['status'] = status_filter
    if request.GET.get('sort'):
        base_params['sort'] = sort_key
        base_params['dir'] = sort_dir

    table_columns = build_team_table_columns(
        is_vp=report_profile == REPORT_PROFILE_OFFICE,
        is_production=report_profile == REPORT_PROFILE_PRODUCTION,
        base_params=base_params,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )

    scope_label = 'SX' if report_profile == REPORT_PROFILE_PRODUCTION else 'VP'
    team_title = 'Quản lý BC (VP)' if report_profile == REPORT_PROFILE_OFFICE else f'Quản lý báo cáo ({scope_label})'
    team_template = (
        'reports/team_cn.html'
        if report_profile == REPORT_PROFILE_PRODUCTION
        else 'reports/team_vp.html'
    )
    return render(request, team_template, {
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'division_choices': division_choices,
        'selected_dept': dept_filter,
        'selected_division': division_filter,
        'status_filter': status_filter,
        'stat_urls': _team_stat_urls(base_params),
        'search_query': search_query,
        'report_date': report_date,
        'range_from': date_from,
        'range_to': date_to,
        'selected_period': period_filter if report_profile == REPORT_PROFILE_OFFICE else '',
        'period_filter_choices': PERIOD_CHOICES if report_profile == REPORT_PROFILE_OFFICE else [],
        'submitted_count': submitted,
        'missing_count': missing,
        'no_report_count': no_report_count,
        'reviewed_count': reviewed_count,
        'not_reviewed_count': not_reviewed_count,
        'rejected_count': rejected_count,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
        'report_period': report_period,
        'reports_scope_label': scope_label,
        'team_page_title': team_title,
        'office_period': report_period if report_profile == REPORT_PROFILE_OFFICE else PERIOD_DAY,
        'period_query': (
            base_params
            if report_profile == REPORT_PROFILE_OFFICE
            else team_date_range_query_params(date_from, date_to)
        ),
        'today_url_name': (
            'reports:today_cn'
            if report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:today_vp'
        ),
        'detail_url_name': (
            'reports:detail_cn'
            if report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:detail_vp'
        ),
        'team_url_name': team_url_name_for_profile(report_profile),
        'table_columns': table_columns,
        'team_sort_key': sort_key,
        'team_sort_dir': sort_dir,
        'team_sort_active': bool(request.GET.get('sort')),
        'team_list_query': urlencode(base_params),
        'summary_list_query': (
            urlencode(_summary_list_query_params(dept_filter=dept_filter))
            if report_profile == REPORT_PROFILE_PRODUCTION
            else ''
        ),
        'my_url_name': (
            'reports:my_cn'
            if report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:my_vp'
        ),
    })


@_reports_access_required
def team_weekly_reports_redirect(request):
    return redirect(redirect_team_weekly_legacy(request.user))


@_reports_access_required
def team_weekly_reports_cn(request):
    return redirect('reports:team_cn')


@_reports_access_required
def team_weekly_reports_vp(request):
    period = request.GET.get('period') or PERIOD_WEEK
    date_from = _parse_iso_date(request.GET.get('from'))
    date_to = _parse_iso_date(request.GET.get('to'))
    if not date_from or not date_to:
        anchor = parse_period_anchor_date(request, period)
        if period == PERIOD_MONTH:
            from calendar import monthrange

            date_from = anchor
            last_day = monthrange(anchor.year, anchor.month)[1]
            date_to = anchor.replace(day=last_day)
        elif period == PERIOD_WEEK:
            date_from = anchor
            date_to = anchor + timedelta(days=6)
        else:
            date_from, date_to = parse_team_date_range(request)
    params = team_date_range_query_params(date_from, date_to)
    query = request.META.get('QUERY_STRING', '').strip()
    if query:
        extra = dict(
            x.split('=', 1)
            for x in query.split('&')
            if '=' in x and x.split('=', 1)[0] not in params
        )
        params.update(extra)
    return redirect(f'{reverse("reports:team_vp")}?{urlencode(params)}')


def _team_weekly_reports_for_profile(request, report_profile: str):
    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        if can_submit_daily_report(request.user):
            return redirect(weekly_url_for_profile(report_profile))
        return redirect('home_portal')

    week_start = _parse_week_start(request)
    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    division_filter = (request.GET.get('division') or '').strip()
    status_filter = _parse_team_status_filter(request)
    team_base = _team_queryset(request.user, search_query, report_profile=report_profile)
    division_choices = division_filter_choices_from_team(
        request.user,
        team_base,
        dept_filter=dept_filter,
    )
    team = (
        filter_users_by_division(team_base, division_filter)
        if division_filter else team_base
    )
    all_team_ids = list(team.values_list('id', flat=True))
    all_reports = meaningful_weekly_reports_qs().filter(
        employee_id__in=all_team_ids,
        week_start=week_start,
        report_profile=report_profile,
    )
    team_count = team.count()
    submitted = all_reports.filter(status=WeeklyWorkReport.STATUS_SUBMITTED).count()
    missing = team_count - submitted

    reports = meaningful_weekly_reports_qs().filter(
        employee_id__in=all_team_ids,
        week_start=week_start,
        report_profile=report_profile,
    ).select_related('employee', 'employee__profile').annotate(
        attachment_count=Count('attachments'),
    )
    report_map = {r.employee_id: r for r in reports}
    department_groups, dept_choices = _build_department_group_rows(
        request.user,
        team,
        report_map,
        weekly_report_visible_to_team,
        dept_filter=dept_filter,
    )
    department_groups = _filter_team_department_groups(
        department_groups,
        status_filter,
        submitted_status=WeeklyWorkReport.STATUS_SUBMITTED,
    )

    base_params = {'week': week_start.isoformat()}
    if search_query:
        base_params['q'] = search_query
    if dept_filter:
        base_params['dept'] = dept_filter
    if division_filter:
        base_params['division'] = division_filter

    ctx = _weekly_context_common(request, week_start, report_profile=report_profile)
    ctx.update({
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'division_choices': division_choices,
        'selected_dept': dept_filter,
        'selected_division': division_filter,
        'status_filter': status_filter,
        'stat_urls': _team_stat_urls(base_params),
        'search_query': search_query,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
        'report_period': 'weekly',
    })
    return render(request, 'reports/team_weekly.html', ctx)


def _report_history_url_for(report, viewer) -> str:
    return history_url_for(report, viewer)


def _can_export_report_detail(report, hourly_grid, productivity, office_sheet) -> bool:
    from reports.excel_export import can_export_daily_report
    from reports.office_content import spreadsheet_has_content

    if not can_export_daily_report(report):
        return False
    if report.is_production_report:
        has_grid = bool(hourly_grid and hourly_grid.get('rows'))
        has_productivity = bool(productivity and productivity.get('has_data'))
        return has_grid or has_productivity
    return spreadsheet_has_content(office_sheet) or bool((report.document_html or '').strip()) or report.attachments.exists()


def _report_detail_core(request, pk, *, detail_url_name: str):
    from reports.production_hourly import (
        build_hourly_grid,
        build_productivity_report,
        can_edit_production_norms,
        can_edit_production_report,
        can_manager_edit_unsubmitted_production_report,
        parse_decimal,
        delete_production_products,
        update_product_norms,
        update_production_product_fields,
        report_has_manager_fixable_anomaly,
    )

    report = get_object_or_404(
        DailyWorkReport.objects.select_related(
            'employee',
            'employee__profile',
            'proxy_entered_by',
            'proxy_entered_by__profile',
        ).prefetch_related(
            'lines',
            'attachments',
            'production_products__hourly_entries',
            'production_products__updated_by',
            'production_products__updated_by__profile',
        ),
        pk=pk,
    )
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo này.')
        return redirect('reports:hub')

    if report.is_production_report:
        from reports.report_lock import ensure_production_report_approval_state

        if ensure_production_report_approval_state(report):
            report.refresh_from_db()

    can_review = can_review_user_report(request.user, report)
    can_edit_norm = can_edit_production_norms(request.user, report)
    list_query = team_list_query_from_request(request)
    is_rejected = bool(report.is_production_report and report.is_hod_rejected)
    can_approve = (
        can_edit_norm
        and report.is_production_report
        and report.status == DailyWorkReport.STATUS_SUBMITTED
        and not report.hod_reviewed
        and not is_rejected
    )
    can_unapprove = (
        can_edit_norm
        and report.is_production_report
        and report.status == DailyWorkReport.STATUS_SUBMITTED
        and report.hod_reviewed
        and not is_rejected
    )

    def _detail_redirect():
        query = team_list_query_from_request(request)
        url = reverse(detail_url_name, args=[pk])
        if query:
            return redirect(f'{url}?{query}')
        return redirect(detail_url_name, pk=pk)

    if (
        request.method == 'GET'
        and not report.is_production_report
        and lock_report_on_supervisor_view(report, request.user)
    ):
        report.refresh_from_db()

    if (
        request.method == 'POST'
        and request.POST.get('action') == 'approve_report'
        and can_approve
    ):
        from reports.report_lock import approve_production_report

        approve_production_report(report)
        messages.success(
            request,
            'Đã duyệt báo cáo. Bấm Hoàn duyệt nếu cần mở lại cho nhân viên chỉnh sửa.',
        )
        return _detail_redirect()

    if (
        request.method == 'POST'
        and request.POST.get('action') == 'unapprove_report'
        and can_unapprove
    ):
        from reports.report_lock import unapprove_production_report

        unapprove_production_report(report)
        return _detail_redirect()

    # Đánh dấu nhận xét đã đọc (comment không phải của mình)
    if request.method == 'GET':
        ReportComment.objects.filter(
            daily_report=report, is_read=False,
        ).exclude(author=request.user).update(is_read=True)

    if request.method == 'POST' and request.POST.get('action') == 'update_norms' and can_edit_norm:
        if report.is_production_report and report.is_hod_rejected:
            messages.error(request, 'Báo cáo không được duyệt — không thể chỉnh sửa.')
            return _detail_redirect()
        if report.is_production_report and report.status != DailyWorkReport.STATUS_SUBMITTED:
            messages.error(request, 'Chỉ có thể chỉnh sửa định mức sau khi nhân viên đã nộp báo cáo.')
            return _detail_redirect()
        delete_ids = [
            int(key[15:])
            for key, val in request.POST.items()
            if key.startswith('delete_product_') and val and key[15:].isdigit()
        ]

        norms = {}
        codes = {}
        processes = {}
        skip_ids = set(delete_ids)
        for key, value in request.POST.items():
            if key.startswith('norm_'):
                product_id = key[5:]
                if not product_id.isdigit() or int(product_id) in skip_ids:
                    continue
                norm = parse_decimal(value)
                if norm and norm > 0:
                    norms[int(product_id)] = norm
            elif key.startswith('code_'):
                product_id = key[5:]
                if product_id.isdigit() and int(product_id) not in skip_ids:
                    codes[int(product_id)] = value
            elif key.startswith('process_'):
                product_id = key[8:]
                if product_id.isdigit() and int(product_id) not in skip_ids:
                    processes[int(product_id)] = value

        from reports.production_edit_log import collect_productivity_update_detail

        change_detail = collect_productivity_update_detail(
            report,
            delete_ids,
            norms,
            codes,
            processes,
        )
        deleted = delete_production_products(report, delete_ids)
        count = update_production_product_fields(
            report,
            norms_by_id=norms,
            codes_by_id=codes,
            processes_by_id=processes,
            updated_by=request.user,
        )
        if deleted and count:
            messages.success(
                request,
                f'Đã xóa {deleted} công đoạn và cập nhật {count} dòng.',
            )
        elif deleted:
            messages.success(request, f'Đã xóa {deleted} công đoạn.')
        elif count:
            messages.success(request, f'Đã cập nhật {count} dòng mã hàng / công đoạn.')
        else:
            messages.warning(request, 'Không có thay đổi hợp lệ để cập nhật.')
        if deleted or count:
            from reports.models import DailyWorkReportEditLog
            from reports.report_edit_log import log_report_edit

            parts = []
            if deleted:
                parts.append(f'xóa {deleted} công đoạn')
            if count:
                parts.append(f'cập nhật {count} dòng mã hàng / công đoạn')
            log_report_edit(
                report,
                request.user,
                summary='Quản lý ' + ' và '.join(parts) + '.',
                detail=change_detail,
            )
        return _detail_redirect()

    can_comment = can_review or report.employee_id == request.user.id
    if (
        request.method == 'POST'
        and request.POST.get('action') == 'add_comment'
        and can_comment
    ):
        return _handle_add_report_comment(
            request,
            report=report,
            daily_report=report,
            can_review=can_review,
            redirect_fn=_detail_redirect,
        )

    from reports.office_content import (
        document_has_any_content,
        links_has_content,
        normalize_spreadsheet_json,
        prepare_document_html_for_display,
        spreadsheet_has_content,
    )

    office_sheet = normalize_spreadsheet_json(report.spreadsheet_json)
    document_html_display = ''
    tab_attachments = _daily_attachments_by_tab(report) if not report.is_production_report else None
    bang_detail_images, bang_detail_files = tab_attachments['bang'] if tab_attachments else ([], [])
    vanban_detail_images, vanban_detail_files = tab_attachments['vanban'] if tab_attachments else ([], [])
    link_detail_images, link_detail_files = tab_attachments['link'] if tab_attachments else ([], [])
    if not report.is_production_report and document_has_any_content(report.document_html or ''):
        document_html_display = prepare_document_html_for_display(
            report.document_html,
            report,
            request,
        )
    has_office_document = (
        not report.is_production_report
        and (
            document_has_any_content(report.document_html or '')
            or vanban_detail_images
            or vanban_detail_files
        )
    )
    has_office_spreadsheet = (
        not report.is_production_report
        and (
            spreadsheet_has_content(office_sheet)
            or bang_detail_images
            or bang_detail_files
        )
    )
    office_sheet_has_data = (
        not report.is_production_report and spreadsheet_has_content(office_sheet)
    )
    hourly_grid = None
    productivity = None
    edit_report_url = ''
    if report.is_production_report and (
        report.shift_started_at
        or report.production_products.exists()
    ):
        hourly_grid = build_hourly_grid(report)
        productivity = build_productivity_report(report)

    def _production_edit_query(report) -> str:
        if report.is_production_report and report.status == DailyWorkReport.STATUS_SUBMITTED:
            return '&phase=review&edit_content=1'
        return ''

    can_submit = can_submit_daily_report(request.user)
    if can_edit_own_daily_report(request.user, report, can_submit=can_submit):
        if report.is_production_report:
            edit_report_url = (
                f"{reverse('reports:today_cn')}?date={report.report_date.isoformat()}"
                f"&shift={report.shift}"
                f"&from_detail={report.pk}"
                f"{_production_edit_query(report)}"
            )
        else:
            edit_report_url = (
                f"{reverse('reports:today_vp')}"
                f"?{urlencode(period_query_param(report.report_period, report.report_date))}"
            )
    elif (
        report.is_production_report
        and can_edit_norm
        and can_edit_production_report(
            request.user,
            report,
            can_submit=can_submit,
        )
    ):
        edit_report_url = (
            f"{reverse('reports:proxy_cn')}?date={report.report_date.isoformat()}"
            f"&shift={report.shift}"
            f"&for_user={report.employee_id}"
            f"&from_detail={report.pk}"
        )
    elif (
        report.is_production_report
        and can_manager_edit_unsubmitted_production_report(request.user, report)
    ):
        edit_report_url = (
            f"{reverse('reports:proxy_cn')}?date={report.report_date.isoformat()}"
            f"&shift={report.shift}"
            f"&for_user={report.employee_id}"
            f"&from_detail={report.pk}"
        )
    if report.is_production_report and (report.hod_reviewed or report.is_hod_rejected):
        edit_report_url = ''
    detail_template = (
        'reports/detail_cn.html'
        if report.is_production_report
        else 'reports/detail_vp.html'
    )
    return render(request, detail_template, {
        'report': report,
        'office_sheet': office_sheet,
        'document_html_display': document_html_display,
        'link_previews': link_preview_rows(report.links) if not report.is_production_report else [],
        'has_office_document': has_office_document,
        'has_office_spreadsheet': has_office_spreadsheet,
        'office_sheet_has_data': office_sheet_has_data,
        'has_office_links': (
            not report.is_production_report and links_has_content(report.links or '')
        ),
        'has_office_link_attachments': (
            not report.is_production_report
            and (link_detail_images or link_detail_files)
        ),
        'tab_attachments': tab_attachments,
        'bang_detail_images': bang_detail_images,
        'bang_detail_files': bang_detail_files,
        'vanban_detail_images': vanban_detail_images,
        'vanban_detail_files': vanban_detail_files,
        'link_detail_images': link_detail_images,
        'link_detail_files': link_detail_files,
        'hourly_grid': hourly_grid,
        'productivity': productivity,
        'edit_report_url': edit_report_url,
        'production_has_anomaly': (
            report.is_production_report
            and report.status != DailyWorkReport.STATUS_SUBMITTED
            and report_has_manager_fixable_anomaly(report)
        ),
        'can_review': can_review,
        'can_approve': can_approve,
        'can_unapprove': can_unapprove,
        'can_comment': can_comment,
        'comments': _report_comments_queryset(report),
        'can_edit_norm': can_edit_norm,
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
        'history_url': history_url_for(report, request.user),
        'export_url': detail_export_url_for_report(report),
        'can_export_report': _can_export_report_detail(report, hourly_grid, productivity, office_sheet),
        'list_back_url': team_list_back_url_for(
            report,
            request.user,
            can_view_team=can_view_team_reports(request.user),
            list_query=list_query,
        ),
        'team_list_query': list_query,
        'shift_badge_class': (
            shift_badge_class(report.shift)
            if report.is_production_report and report.shift else ''
        ),
        'production_day_shift_tabs': (
            build_production_day_shift_tabs(
                report,
                detail_url_name=detail_url_name,
                list_query=list_query,
            )
            if report.is_production_report else []
        ),
    })


def _report_edit_history_core(request, pk, *, detail_url_name: str):
    report = get_object_or_404(
        DailyWorkReport.objects.select_related('employee', 'employee__profile'),
        pk=pk,
    )
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo này.')
        return redirect('reports:hub')

    list_query = team_list_query_from_request(request)
    detail_url = reverse(detail_url_name, kwargs={'pk': pk})
    if list_query:
        detail_url = f'{detail_url}?{list_query}'

    return render(request, 'reports/report_edit_history.html', {
        'report': report,
        'edit_logs': report.edit_logs.select_related('edited_by', 'edited_by__profile'),
        'detail_url': detail_url,
        'list_back_url': team_list_back_url_for(
            report,
            request.user,
            can_view_team=can_view_team_reports(request.user),
            list_query=list_query,
        ),
        'shift_badge_class': (
            shift_badge_class(report.shift)
            if report.is_production_report and report.shift else ''
        ),
    })


@_reports_access_required
def report_edit_history_cn(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if not report.is_production_report:
        return redirect('reports:detail_vp_changelog', pk=pk)
    return _report_edit_history_core(request, pk, detail_url_name='reports:detail_cn')


@_reports_access_required
def report_edit_history_vp(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:detail_cn_changelog', pk=pk)
    return _report_edit_history_core(request, pk, detail_url_name='reports:detail_vp')


@_reports_access_required
def report_detail_cn(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if not report.is_production_report:
        return redirect('reports:detail_vp', pk=pk)
    return _report_detail_core(request, pk, detail_url_name='reports:detail_cn')


@_reports_access_required
def report_detail_vp(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:detail_cn', pk=pk)
    return _report_detail_core(request, pk, detail_url_name='reports:detail_vp')


@_reports_access_required
def report_detail(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:detail_cn', pk=pk)
    return redirect('reports:detail_vp', pk=pk)


def _report_detail_export_core(request, pk, *, detail_url_name: str):
    from reports.excel_export import can_export_daily_report, export_daily_report_xlsx

    report = get_object_or_404(
        DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related(
            'production_products__hourly_entries',
        ),
        pk=pk,
    )
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xuất báo cáo này.')
        return redirect('reports:hub')
    if not can_export_daily_report(report):
        messages.warning(request, 'Báo cáo chưa có dữ liệu để xuất Excel.')
        return redirect(detail_url_name, pk=pk)
    return export_daily_report_xlsx(report)


@_reports_access_required
def report_detail_export_cn(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if not report.is_production_report:
        return redirect('reports:detail_export_vp', pk=pk)
    return _report_detail_export_core(request, pk, detail_url_name='reports:detail_cn')


@_reports_access_required
def report_detail_export_vp(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:detail_export_cn', pk=pk)
    return _report_detail_export_core(request, pk, detail_url_name='reports:detail_vp')


@_reports_access_required
def report_detail_export(request, pk):
    report = get_object_or_404(DailyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:detail_export_cn', pk=pk)
    return redirect('reports:detail_export_vp', pk=pk)


@_require_today_report_access
def today_report_cn(request):
    if request.GET.get('for_user'):
        from django.utils.http import urlencode as _urlencode
        params = {'for_user': request.GET.get('for_user')}
        if request.GET.get('date'):
            params['date'] = request.GET.get('date')
        if request.GET.get('shift'):
            params['shift'] = request.GET.get('shift')
        if request.GET.get('edit_content') == '1':
            params['edit_content'] = '1'
        if request.GET.get('from_detail'):
            params['from_detail'] = request.GET.get('from_detail')
        return redirect(f"{reverse('reports:proxy_cn')}?{_urlencode(params)}")
    report_date = _parse_report_date(request)
    return _today_production_report(request, report_date)


@_require_today_report_access
def today_report_vp(request):
    report_period = parse_office_period(request)
    report_date = parse_period_anchor_date(request, report_period)
    return _today_office_report(request, report_date, report_period=report_period)


@_require_submit_access
def copy_yesterday_cn(request):
    return copy_yesterday(request, report_profile=REPORT_PROFILE_PRODUCTION)


@_require_submit_access
def copy_yesterday_vp(request):
    return copy_yesterday(request, report_profile=REPORT_PROFILE_OFFICE)


@_require_submit_access
def copy_yesterday_redirect(request):
    return redirect(redirect_copy_yesterday_legacy(request.user))


@_reports_access_required
def weekly_report_detail_redirect(request, pk):
    report = get_object_or_404(WeeklyWorkReport, pk=pk)
    if report.is_production_report:
        return redirect('reports:weekly_detail_cn', pk=pk, permanent=True)
    return redirect('reports:weekly_detail_vp', pk=pk, permanent=True)


@_reports_access_required
def weekly_report_detail_cn(request, pk):
    return _weekly_report_detail_core(request, pk, detail_url_name='reports:weekly_detail_cn')


@_reports_access_required
def weekly_report_detail_vp(request, pk):
    return _weekly_report_detail_core(request, pk, detail_url_name='reports:weekly_detail_vp')


def _weekly_report_detail_core(request, pk, *, detail_url_name: str):
    report = get_object_or_404(
        WeeklyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related('attachments'),
        pk=pk,
    )
    if not can_view_user_weekly_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo tuần này.')
        return redirect('reports:hub')
    team_weekly_url_name = team_weekly_url_name_for_profile(report.report_profile)
    if not weekly_report_visible_to_team(report) and report.employee_id != request.user.id:
        messages.info(request, 'Nhân viên chưa lưu nháp hoặc gửi báo cáo tuần.')
        return redirect(f'{reverse(team_weekly_url_name)}?week={report.week_start.isoformat()}')

    can_review = can_review_user_weekly_report(request.user, report)

    if request.method == 'GET' and lock_report_on_supervisor_view(report, request.user):
        report.refresh_from_db()

    # Đánh dấu nhận xét đã đọc (comment không phải của mình)
    if request.method == 'GET':
        ReportComment.objects.filter(
            weekly_report=report, is_read=False,
        ).exclude(author=request.user).update(is_read=True)

    can_comment = can_review or report.employee_id == request.user.id
    if (
        request.method == 'POST'
        and request.POST.get('action') == 'add_comment'
        and can_comment
    ):
        return _handle_add_report_comment(
            request,
            report=report,
            weekly_report=report,
            can_review=can_review,
            redirect_fn=lambda: redirect(detail_url_name, pk=pk),
        )

    images, files = _weekly_attachments(report)
    profile = report.employee.profile
    edit_report_url = ''
    can_submit = can_submit_daily_report(request.user)
    if can_edit_own_weekly_report(request.user, report, can_submit=can_submit):
        edit_report_url = (
            f"{reverse(weekly_url_name_for_profile(report.report_profile))}"
            f"?week={report.week_start.isoformat()}"
        )
    return render(request, 'reports/weekly_detail.html', {
        'report': report,
        'weekly_images': images,
        'weekly_files': files,
        'link_previews': link_preview_rows(report.links),
        'file_previews': [file_attachment_preview(f) for f in files],
        'image_previews': [file_attachment_preview(i) for i in images],
        'week_label': week_label(report.week_start),
        'employee_name': profile.full_name if profile else report.employee.username,
        'department_name': profile.department.name if profile and profile.department_id else '',
        'can_review': can_review,
        'can_comment': can_comment,
        'comments': _report_comments_queryset(report),
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
        'edit_report_url': edit_report_url,
        'report_period': 'weekly',
        'report_date': report.week_start,
        'week_start': report.week_start,
        'reports_scope_label': report_profile_label(report.report_profile),
        'team_weekly_url_name': team_weekly_url_name,
        'my_url_name': my_url_name_for_profile(report.report_profile),
    })


@_reports_access_required
def document_image_serve(request, report_pk, relpath):
    import mimetypes

    report = get_object_or_404(DailyWorkReport, pk=report_pk)
    if not can_view_user_report(request.user, report):
        raise Http404
    if not daily_report_visible_to_team(report) and report.employee_id != request.user.id:
        raise Http404

    rel = unquote(relpath or '').lstrip('/')
    if not is_inline_image_relpath(rel):
        raise Http404
    if not inline_image_exists(rel):
        raise Http404

    content_type = mimetypes.guess_type(rel)[0] or 'application/octet-stream'
    file_handle = open_inline_image(rel)
    return FileResponse(file_handle, content_type=content_type)


@_reports_access_required
def inline_image_serve(request, relpath):
    """Ảnh inline khi soạn thảo — trước khi có URL chi tiết báo cáo."""
    import mimetypes

    rel = unquote(relpath or '').lstrip('/')
    if not can_view_inline_image(request.user, rel):
        raise Http404
    if not inline_image_exists(rel):
        raise Http404
    content_type = mimetypes.guess_type(rel)[0] or 'application/octet-stream'
    return FileResponse(open_inline_image(rel), content_type=content_type)


@_reports_access_required
def daily_attachment_preview(request, pk):
    from nas_storage.file_preview import inline_office_pdf_response, inline_pdf_response, preview_kind
    from tools.services import office_preview_available

    att = get_object_or_404(
        DailyWorkReportAttachment.objects.select_related('report__employee'),
        pk=pk,
    )
    report = att.report
    if not can_view_user_report(request.user, report):
        raise Http404
    if not daily_report_visible_to_team(report) and report.employee_id != request.user.id:
        raise Http404

    path = daily_attachment_abs_path(att)
    if not path:
        raise Http404

    kind = preview_kind(att.display_name)
    if kind == 'pdf':
        return inline_pdf_response(path, filename=att.display_name)
    if kind == 'office' and office_preview_available():
        return inline_office_pdf_response(path, display_name=att.display_name)
    raise Http404


@_reports_access_required
def daily_attachment_serve(request, pk):
    import mimetypes

    att = get_object_or_404(
        DailyWorkReportAttachment.objects.select_related('report__employee'),
        pk=pk,
    )
    report = att.report
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền tải file này.')
        return redirect('reports:hub')
    if not daily_report_visible_to_team(report) and report.employee_id != request.user.id:
        raise Http404

    path = daily_attachment_abs_path(att)
    if not path:
        raise Http404

    content_type = mimetypes.guess_type(att.display_name)[0] or 'application/octet-stream'
    inline_types = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/svg+xml',
    }
    force_download = request.GET.get('download', '').lower() in ('1', 'true', 'yes')
    as_attachment = force_download or content_type not in inline_types
    file_handle = open_daily_attachment(att)
    response = FileResponse(file_handle, content_type=content_type, as_attachment=as_attachment)
    if as_attachment:
        from reports.weekly_preview import attachment_content_disposition

        response['Content-Disposition'] = attachment_content_disposition(att.display_name)
    return response


@_reports_access_required
def weekly_attachment_preview(request, pk):
    from nas_storage.file_preview import inline_office_pdf_response, inline_pdf_response, preview_kind
    from tools.services import office_preview_available

    att = get_object_or_404(
        WeeklyWorkReportAttachment.objects.select_related('report__employee'),
        pk=pk,
    )
    report = att.report
    if not can_view_user_weekly_report(request.user, report):
        raise Http404
    if not weekly_report_visible_to_team(report) and report.employee_id != request.user.id:
        raise Http404

    path = weekly_attachment_abs_path(att)
    if not path:
        raise Http404

    kind = preview_kind(att.display_name)
    if kind == 'pdf':
        return inline_pdf_response(path, filename=att.display_name)
    if kind == 'office' and office_preview_available():
        return inline_office_pdf_response(path, display_name=att.display_name)
    raise Http404


@_reports_access_required
def weekly_attachment_serve(request, pk):
    import mimetypes

    att = get_object_or_404(
        WeeklyWorkReportAttachment.objects.select_related('report__employee'),
        pk=pk,
    )
    report = att.report
    if not can_view_user_weekly_report(request.user, report):
        messages.error(request, 'Bạn không có quyền tải file này.')
        return redirect('reports:hub')
    if not weekly_report_visible_to_team(report) and report.employee_id != request.user.id:
        raise Http404

    path = weekly_attachment_abs_path(att)
    if not path:
        raise Http404

    content_type = mimetypes.guess_type(att.display_name)[0] or 'application/octet-stream'
    inline_types = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/svg+xml',
    }
    force_download = request.GET.get('download', '').lower() in ('1', 'true', 'yes')
    as_attachment = force_download or content_type not in inline_types
    file_handle = open_weekly_attachment(att)
    response = FileResponse(file_handle, content_type=content_type, as_attachment=as_attachment)
    if as_attachment:
        from reports.weekly_preview import attachment_content_disposition

        response['Content-Disposition'] = attachment_content_disposition(att.display_name)
    return response


@_reports_access_required
def comment_attachment_preview(request, pk):
    from nas_storage.file_preview import inline_office_pdf_response, inline_pdf_response, preview_kind
    from reports.comment_nas_storage import comment_attachment_abs_path
    from tools.services import office_preview_available

    att = get_object_or_404(
        ReportCommentAttachment.objects.select_related(
            'comment__daily_report__employee',
            'comment__weekly_report__employee',
        ),
        pk=pk,
    )
    if not _can_view_comment_attachment(request.user, att):
        raise Http404

    path = comment_attachment_abs_path(att)
    if not path:
        raise Http404

    kind = preview_kind(att.display_name)
    if kind == 'pdf':
        return inline_pdf_response(path, filename=att.display_name)
    if kind == 'office' and office_preview_available():
        return inline_office_pdf_response(path, display_name=att.display_name)
    raise Http404


@_reports_access_required
def comment_attachment_serve(request, pk):
    import mimetypes

    from reports.comment_nas_storage import comment_attachment_abs_path, open_comment_attachment

    att = get_object_or_404(
        ReportCommentAttachment.objects.select_related(
            'comment__daily_report__employee',
            'comment__weekly_report__employee',
        ),
        pk=pk,
    )
    if not _can_view_comment_attachment(request.user, att):
        messages.error(request, 'Bạn không có quyền tải file này.')
        return redirect('reports:hub')

    path = comment_attachment_abs_path(att)
    if not path:
        raise Http404

    content_type = mimetypes.guess_type(att.display_name)[0] or 'application/octet-stream'
    inline_types = {
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/svg+xml',
    }
    force_download = request.GET.get('download', '').lower() in ('1', 'true', 'yes')
    as_attachment = force_download or content_type not in inline_types
    file_handle = open_comment_attachment(att)
    response = FileResponse(file_handle, content_type=content_type, as_attachment=as_attachment)
    if as_attachment:
        from reports.weekly_preview import attachment_content_disposition

        response['Content-Disposition'] = attachment_content_disposition(att.display_name)
    return response


def redirect_legacy_cn_today(request):
    return redirect(reverse('reports:today_cn'), permanent=True)


def redirect_legacy_cn_team(request):
    return redirect(reverse('reports:team_cn'), permanent=True)


def redirect_legacy_cn_my(request):
    return redirect(reverse('reports:my_cn'), permanent=True)


def redirect_legacy_cn_copy_yesterday(request):
    return redirect(reverse('reports:copy_yesterday_cn'), permanent=True)


def redirect_legacy_cn_detail(request, pk):
    return redirect(reverse('reports:detail_cn', kwargs={'pk': pk}), permanent=True)


def redirect_legacy_cn_export(request, pk):
    return redirect(reverse('reports:detail_export_cn', kwargs={'pk': pk}), permanent=True)

