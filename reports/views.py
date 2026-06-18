import os
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib import messages
from django.db.models import Count, Sum, Q

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import (
    can_review_user_report,
    can_review_user_weekly_report,
    can_submit_daily_report,
    can_view_team_reports,
    can_view_user_report,
    can_view_user_weekly_report,
    get_report_team_users,
    is_director,
)
from PortalJustPlay.list_search import apply_combined_search, apply_term_search, apply_user_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from reports.report_profile import (
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
)
from reports.navigation import (
    detail_export_url_for_report,
    detail_url_for_report,
    history_url_for,
    list_back_url_for,
    redirect_team_legacy,
    today_url_for_user,
    today_url_name_for_user,
    team_url_for_profile,
    my_url_for_profile,
    my_url_for_user,
    my_url_name_for_profile,
    redirect_copy_yesterday_legacy,
    team_url_name_for_profile,
)
from reports.week_utils import monday_of, parse_week_start, week_end, week_label

from .forms import (
    DailyWorkReportForm,
    DailyWorkReportLineFormSet,
    OfficeDailyWorkReportForm,
    WeeklyWorkReportForm,
)
from .models import DailyWorkReport, WeeklyWorkReport, WeeklyWorkReportAttachment
from .team_utils import (
    build_report_team_department_groups,
    daily_report_visible_to_team,
    department_filter_choices,
    meaningful_daily_reports_qs,
    meaningful_weekly_reports_qs,
    weekly_report_visible_to_team,
)
from .weekly_preview import file_attachment_preview, link_preview_rows
from .weekly_nas_storage import ensure_weekly_report_nas_dir, open_weekly_attachment, weekly_attachment_abs_path
from .weekly_uploads import copy_weekly_attachments, save_weekly_uploads, weekly_report_has_content

User = get_user_model()


_CK5_IMAGE_TYPES = frozenset({'image/jpeg', 'image/png', 'image/gif', 'image/webp'})
_CK5_IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp'})
_CK5_MAX_BYTES = 5 * 1024 * 1024


def _reports_access_required(view_func):
    return module_perm_required(MODULE_REPORTS, 'view')(view_func)


_WEEKLY_SUBMIT_VIEWS = frozenset({'weekly_report', 'copy_prev_week'})


def _is_supervisor_entry_request(request):
    """Cấp trên nhập báo cáo hộ NV (?for_user=)."""
    from reports.production_hourly import can_proxy_enter_daily_report

    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    if not for_user_id:
        return False
    try:
        target = get_report_team_users(request.user).get(pk=int(for_user_id))
    except (ValueError, TypeError, User.DoesNotExist):
        return False
    return can_proxy_enter_daily_report(request.user, target)


def _require_submit_access(view_func):
    @module_perm_required(MODULE_REPORTS, 'create')
    def wrapper(request, *args, **kwargs):
        if not can_submit_daily_report(request.user):
            if can_view_team_reports(request.user):
                if view_func.__name__ in _WEEKLY_SUBMIT_VIEWS:
                    return redirect('reports:team_weekly')
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


def _report_context_common(request, report_date):
    yesterday = report_date - timedelta(days=1)
    return {
        'report_date': report_date,
        'has_yesterday': DailyWorkReport.objects.filter(
            employee=request.user,
            report_date=yesterday,
        ).exists(),
        'yesterday': yesterday,
        'can_view_team': can_view_team_reports(request.user),
    }


def _daily_report_defaults(report_profile: str):
    return {
        'shift': '',
        'report_profile': report_profile,
        'status': DailyWorkReport.STATUS_DRAFT,
    }


def _load_daily_report(user, report_date, *, report_profile: str):
    """Chỉ lấy bản ghi đã lưu; loại báo cáo theo trang CN/VP, không theo phòng ban."""
    try:
        return DailyWorkReport.objects.get(employee=user, report_date=report_date)
    except DailyWorkReport.DoesNotExist:
        return DailyWorkReport(
            employee=user,
            report_date=report_date,
            **_daily_report_defaults(report_profile),
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
    }


def _parse_week_start(request):
    raw = request.GET.get('week') or request.POST.get('week_start')
    return parse_week_start(raw)


def _load_weekly_report(user, week_start):
    try:
        return WeeklyWorkReport.objects.get(employee=user, week_start=week_start)
    except WeeklyWorkReport.DoesNotExist:
        return WeeklyWorkReport(employee=user, week_start=week_start)


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


def _delete_weekly_attachments(report, attachment_ids):
    if not attachment_ids:
        return 0
    qs = report.attachments.filter(pk__in=attachment_ids)
    count = qs.count()
    for att in qs:
        att.file.delete(save=False)
    qs.delete()
    return count


def _weekly_context_common(request, week_start):
    prev_week = week_start - timedelta(days=7)
    return {
        'week_start': week_start,
        'week_end': week_end(week_start),
        'week_label': week_label(week_start),
        'has_prev_week': WeeklyWorkReport.objects.filter(
            employee=request.user,
            week_start=prev_week,
        ).exists(),
        'prev_week': prev_week,
        'can_view_team': can_view_team_reports(request.user),
        'report_period': 'weekly',
    }


def _today_production_report(request, report_date):
    from reports.views_production_hourly import today_production_hourly
    return today_production_hourly(request, report_date, _report_context_common)


def _today_office_report(request, report_date):
    from hrm.permissions import get_profile as load_profile
    user_profile = load_profile(request.user)

    report = _load_daily_report(request.user, report_date, report_profile=REPORT_PROFILE_OFFICE)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        report = _ensure_daily_report_saved(report)
        form = OfficeDailyWorkReportForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save(commit=False)
            report.report_profile = REPORT_PROFILE_OFFICE
            report.shift = ''
            messages.success(request, _finalize_report_submission(report, action))
            report.save()
            return redirect(f'{reverse("reports:today_vp")}?date={report_date.isoformat()}')
    else:
        form = OfficeDailyWorkReportForm(instance=report)

    ctx = _report_context_common(request, report_date)
    ctx.update(_ckeditor_context())
    ctx.update({
        'form': form,
        'report': report,
        'employee_name': (user_profile.full_name if user_profile else '') or request.user.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'report_period': 'daily',
        'content_tab_hint': 'Nhập tiêu đề cột ở hàng hồng, số liệu ở từng ô bên dưới.',
        'copy_url': reverse('reports:copy_yesterday_vp') if ctx['has_yesterday'] else None,
        'copy_label': 'Sao chép HQ',
        'copy_confirm': 'Sao chép nội dung từ hôm qua?',
    })
    return render(request, 'reports/today_office.html', ctx)


@_require_submit_access
def weekly_report(request):
    from hrm.permissions import get_profile as load_profile

    week_start = _parse_week_start(request)
    user_profile = load_profile(request.user)
    report = _load_weekly_report(request.user, week_start)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
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
                msg = _finalize_report_submission(report, action)
                messages.success(request, msg)
                report.save()
                ensure_weekly_report_nas_dir()
                save_weekly_uploads(report, image_list=image_uploads, file_list=file_uploads)
                return redirect(f'{reverse("reports:weekly")}?week={week_start.isoformat()}')
    else:
        form = WeeklyWorkReportForm(instance=report)

    images, files = _weekly_attachments(report)
    ctx = _weekly_context_common(request, week_start)
    ctx.update({
        'form': form,
        'report': report,
        'weekly_images': images,
        'weekly_files': files,
        'employee_name': (user_profile.full_name if user_profile else '') or request.user.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'copy_url': reverse('reports:copy_prev_week') if ctx['has_prev_week'] else None,
        'copy_label': 'Sao chép tuần trước',
        'copy_confirm': 'Sao chép nội dung từ tuần trước?',
    })
    return render(request, 'reports/weekly.html', ctx)


@_require_submit_access
def copy_prev_week(request):
    this_week = monday_of(timezone.localdate())
    prev_week = this_week - timedelta(days=7)
    source = WeeklyWorkReport.objects.filter(
        employee=request.user,
        week_start=prev_week,
    ).first()
    if not source:
        messages.warning(request, 'Không có báo cáo tuần trước để sao chép.')
        return redirect('reports:weekly')

    report, _ = WeeklyWorkReport.objects.get_or_create(
        employee=request.user,
        week_start=this_week,
        defaults={'status': WeeklyWorkReport.STATUS_DRAFT},
    )
    report.status = WeeklyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    report.links = source.links
    report.save()
    _delete_weekly_attachments(report, list(report.attachments.values_list('pk', flat=True)))
    copy_weekly_attachments(source, report)
    messages.success(request, 'Đã sao chép báo cáo tuần trước. Kiểm tra và gửi lại.')
    return redirect(f'{reverse("reports:weekly")}?week={this_week.isoformat()}')


def _resolve_today_subject(request):
    subject = request.user
    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    if for_user_id:
        try:
            subject = get_report_team_users(request.user).get(pk=int(for_user_id))
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

    upload = request.FILES.get('upload')
    if not upload:
        return JsonResponse({'error': {'message': 'Không có file.'}}, status=400)
    if upload.content_type not in _CK5_IMAGE_TYPES:
        return JsonResponse({'error': {'message': 'Chỉ chấp nhận ảnh JPG, PNG, GIF, WebP.'}}, status=400)
    if upload.size > _CK5_MAX_BYTES:
        return JsonResponse({'error': {'message': 'Ảnh tối đa 5MB.'}}, status=400)

    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in _CK5_IMAGE_EXTS:
        ext = '.jpg'
    rel_path = default_storage.save(f'reports/ckeditor5/{uuid.uuid4().hex}{ext}', upload)
    url = request.build_absolute_uri(default_storage.url(rel_path))
    if not url.startswith('http') and getattr(settings, 'MEDIA_URL', None):
        url = request.build_absolute_uri(settings.MEDIA_URL + rel_path)
    return JsonResponse({'url': url})


@_require_submit_access
def copy_yesterday(request, *, report_profile: str):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    source = DailyWorkReport.objects.filter(
        employee=request.user,
        report_date=yesterday,
        report_profile=report_profile,
    ).prefetch_related('lines').first()
    if not source:
        messages.warning(request, 'Không có báo cáo hôm qua để sao chép.')
        return redirect(today_url_for_user(request.user))

    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=today,
        defaults=_daily_report_defaults(report_profile),
    )
    report.report_profile = report_profile
    report.shift = ''
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    if report_profile == REPORT_PROFILE_OFFICE:
        report.spreadsheet_json = source.spreadsheet_json
        report.document_html = source.document_html
        report.save()
        report.lines.all().delete()
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
        return redirect(f'{reverse("reports:today_cn")}?date={today.isoformat()}')
    return redirect(f'{reverse("reports:today_vp")}?date={today.isoformat()}')


def _my_reports_period(request):
    period = (request.GET.get('period') or 'daily').strip().lower()
    if period not in ('daily', 'weekly'):
        period = 'daily'
    return period


@_reports_access_required
def my_reports(request):
    return redirect(my_url_for_user(request.user))


@_reports_access_required
def my_reports_cn(request):
    return _my_reports(request, daily_report_profile=REPORT_PROFILE_PRODUCTION)


@_reports_access_required
def my_reports_vp(request):
    return _my_reports(request, daily_report_profile=REPORT_PROFILE_OFFICE)


def _my_reports(request, daily_report_profile=None):
    search_query = get_search_query(request)
    period = _my_reports_period(request)
    subject = request.user
    history_employee_name = ''
    for_user_id = request.GET.get('for_user')
    if for_user_id:
        try:
            subject = get_report_team_users(request.user).get(pk=int(for_user_id))
            profile = getattr(subject, 'profile', None)
            history_employee_name = profile.full_name if profile and profile.full_name else subject.username
        except (ValueError, TypeError, User.DoesNotExist):
            messages.error(request, 'Không tìm thấy nhân viên hoặc bạn không có quyền xem lịch sử.')
            return redirect('reports:hub')
    elif not can_submit_daily_report(request.user):
        if can_view_team_reports(request.user):
            return redirect(redirect_team_legacy(request.user))
        return redirect('home_portal')

    if period == 'weekly':
        reports_qs = meaningful_weekly_reports_qs().filter(
            employee=subject,
        ).annotate(
            attachment_count=Count('attachments'),
        ).order_by('-week_start')
        reports_qs = apply_combined_search(reports_qs, search_query, lambda term: (
            Q(hod_note__icontains=term)
            | Q(status__icontains=term)
            | Q(links__icontains=term)
        ))
    else:
        reports_qs = DailyWorkReport.objects.filter(
            employee=subject,
        )
        if daily_report_profile:
            reports_qs = reports_qs.filter(report_profile=daily_report_profile)
        reports_qs = reports_qs.annotate(
            line_count=Count('lines'),
            total_qty=Sum('lines__quantity'),
        ).order_by('-report_date')
        reports_qs = apply_combined_search(reports_qs, search_query, lambda term: (
            Q(hod_note__icontains=term)
            | Q(status__icontains=term)
            | Q(lines__area__icontains=term)
            | Q(lines__order_code__icontains=term)
            | Q(lines__product_name__icontains=term)
        ))

    page_obj, query_string = paginate_queryset(request, reports_qs)
    scope_label = 'CN' if daily_report_profile == REPORT_PROFILE_PRODUCTION else 'VP' if daily_report_profile else ''
    return render(request, 'reports/my_reports.html', {
        'reports': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_view_team': can_view_team_reports(request.user),
        'report_period': period,
        'history_employee_name': history_employee_name,
        'history_for_user_id': subject.pk if subject.pk != request.user.pk else None,
        'reports_scope_label': scope_label,
        'today_url_name': (
            'reports:today_cn'
            if daily_report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:today_vp'
        ),
        'detail_url_name': (
            'reports:detail_cn'
            if daily_report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:detail_vp'
        ),
        'my_url_name': my_url_name_for_profile(daily_report_profile) if daily_report_profile else 'reports:my',
        'team_url_name': team_url_name_for_profile(daily_report_profile) if daily_report_profile else 'reports:team_cn',
    })


def _team_queryset(viewer, search_query):
    team = get_report_team_users(viewer).select_related(
        'profile',
        'profile__department',
    ).order_by('profile__department__sort_order', 'profile__full_name', 'username')
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


def _parse_team_status_filter(request) -> str:
    val = (request.GET.get('status') or '').strip().lower()
    if val in (TEAM_STATUS_SUBMITTED, TEAM_STATUS_MISSING):
        return val
    return ''


def _team_row_is_submitted(row, *, submitted_status: str) -> bool:
    report = row.get('report')
    return bool(report and report.status == submitted_status)


def _filter_team_department_groups(department_groups, status_filter: str, *, submitted_status: str):
    if not status_filter:
        return department_groups
    filtered = []
    for group in department_groups:
        rows = [
            row for row in group['rows']
            if (
                _team_row_is_submitted(row, submitted_status=submitted_status)
                if status_filter == TEAM_STATUS_SUBMITTED
                else not _team_row_is_submitted(row, submitted_status=submitted_status)
            )
        ]
        if rows:
            filtered.append({**group, 'rows': rows})
    return filtered


def _team_stat_urls(base_params: dict) -> dict:
    def _url(extra: dict) -> str:
        params = {**base_params, **extra}
        params = {k: v for k, v in params.items() if v not in (None, '')}
        return '?' + urlencode(params)

    return {
        'all': _url({}),
        'submitted': _url({'status': TEAM_STATUS_SUBMITTED}),
        'missing': _url({'status': TEAM_STATUS_MISSING}),
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


def _team_reports_for_profile(request, report_profile: str):
    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        if can_submit_daily_report(request.user):
            return redirect(today_url_for_user(request.user))
        return redirect('home_portal')

    report_date = request.GET.get('date') or timezone.localdate()
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    status_filter = _parse_team_status_filter(request)
    team = _team_queryset(request.user, search_query)
    all_team_ids = list(team.values_list('id', flat=True))
    all_reports = meaningful_daily_reports_qs().filter(
        employee_id__in=all_team_ids,
        report_date=report_date,
        report_profile=report_profile,
    )
    team_count = team.count()
    submitted = all_reports.filter(status=DailyWorkReport.STATUS_SUBMITTED).count()
    missing = team_count - submitted

    reports = meaningful_daily_reports_qs().filter(
        employee_id__in=all_team_ids,
        report_date=report_date,
        report_profile=report_profile,
    ).select_related('employee', 'employee__profile').annotate(
        line_count=Count('lines'),
        total_qty=Sum('lines__quantity'),
    )
    report_map = {r.employee_id: r for r in reports}
    department_groups, dept_choices = _build_department_group_rows(
        request.user,
        team,
        report_map,
        daily_report_visible_to_team,
        dept_filter=dept_filter,
    )
    department_groups = _filter_team_department_groups(
        department_groups,
        status_filter,
        submitted_status=DailyWorkReport.STATUS_SUBMITTED,
    )

    base_params = {'date': report_date.isoformat()}
    if search_query:
        base_params['q'] = search_query
    if dept_filter:
        base_params['dept'] = dept_filter

    scope_label = 'CN' if report_profile == REPORT_PROFILE_PRODUCTION else 'VP'
    return render(request, 'reports/team.html', {
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'selected_dept': dept_filter,
        'status_filter': status_filter,
        'stat_urls': _team_stat_urls(base_params),
        'search_query': search_query,
        'report_date': report_date,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
        'report_period': 'daily',
        'reports_scope_label': scope_label,
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
    })


@_reports_access_required
def team_weekly_reports(request):
    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        if can_submit_daily_report(request.user):
            return redirect('reports:weekly')
        return redirect('home_portal')

    week_start = _parse_week_start(request)
    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    status_filter = _parse_team_status_filter(request)
    team = _team_queryset(request.user, search_query)
    all_team_ids = list(team.values_list('id', flat=True))
    all_reports = meaningful_weekly_reports_qs().filter(
        employee_id__in=all_team_ids,
        week_start=week_start,
    )
    team_count = team.count()
    submitted = all_reports.filter(status=WeeklyWorkReport.STATUS_SUBMITTED).count()
    missing = team_count - submitted

    reports = meaningful_weekly_reports_qs().filter(
        employee_id__in=all_team_ids,
        week_start=week_start,
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

    ctx = _weekly_context_common(request, week_start)
    ctx.update({
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'selected_dept': dept_filter,
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
    return spreadsheet_has_content(office_sheet) or bool((report.document_html or '').strip())


def _report_detail_core(request, pk, *, detail_url_name: str):
    from reports.production_hourly import (
        build_hourly_grid,
        build_productivity_report,
        can_edit_production_norms,
        can_edit_production_report,
        lock_production_report_on_supervisor_view,
        parse_decimal,
        update_product_norms,
    )

    report = get_object_or_404(
        DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related(
            'lines',
            'production_products__hourly_entries',
        ),
        pk=pk,
    )
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo này.')
        return redirect('reports:hub')

    can_review = can_review_user_report(request.user, report)
    can_edit_norm = can_edit_production_norms(request.user, report)

    if (
        request.method == 'GET'
        and report.is_production_report
        and lock_production_report_on_supervisor_view(report, request.user)
    ):
        report.refresh_from_db()

    if request.method == 'POST' and request.POST.get('action') == 'update_norms' and can_edit_norm:
        norms = {}
        for key, value in request.POST.items():
            if not key.startswith('norm_'):
                continue
            product_id = key[5:]
            if not product_id.isdigit():
                continue
            norm = parse_decimal(value)
            if norm and norm > 0:
                norms[int(product_id)] = norm
        count = update_product_norms(report, norms)
        if count:
            messages.success(request, f'Đã cập nhật định mức cho {count} mã hàng.')
        else:
            messages.warning(request, 'Không có định mức hợp lệ để cập nhật.')
        return redirect(detail_url_name, pk=pk)

    if request.method == 'POST' and can_review:
        report.hod_reviewed = request.POST.get('hod_reviewed') == 'on'
        report.hod_note = request.POST.get('hod_note', '').strip()
        report.save()
        messages.success(request, 'Đã cập nhật phản hồi.')
        return redirect(detail_url_name, pk=pk)

    from reports.office_content import normalize_spreadsheet_json

    office_sheet = normalize_spreadsheet_json(report.spreadsheet_json)
    hourly_grid = None
    productivity = None
    edit_report_url = ''
    if report.is_production_report and report.shift_started_at:
        hourly_grid = build_hourly_grid(report)
        productivity = build_productivity_report(report)
    if can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
    ):
        if report.employee_id == request.user.id:
            today_name = (
                'reports:today_cn' if report.is_production_report else 'reports:today_vp'
            )
            edit_report_url = f"{reverse(today_name)}?date={report.report_date.isoformat()}"
        elif can_review:
            today_name = (
                'reports:today_cn' if report.is_production_report else 'reports:today_vp'
            )
            edit_report_url = (
                f"{reverse(today_name)}?date={report.report_date.isoformat()}"
                f"&for_user={report.employee_id}"
            )
    return render(request, 'reports/detail.html', {
        'report': report,
        'office_sheet': office_sheet,
        'hourly_grid': hourly_grid,
        'productivity': productivity,
        'edit_report_url': edit_report_url,
        'can_review': can_review,
        'can_edit_norm': can_edit_norm,
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
        'history_url': history_url_for(report, request.user),
        'export_url': detail_export_url_for_report(report),
        'can_export_report': _can_export_report_detail(report, hourly_grid, productivity, office_sheet),
        'list_back_url': list_back_url_for(
            report,
            request.user,
            can_view_team=can_view_team_reports(request.user),
        ),
    })


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
    report_date = _parse_report_date(request)
    return _today_production_report(request, report_date)


@_require_today_report_access
def today_report_vp(request):
    report_date = _parse_report_date(request)
    return _today_office_report(request, report_date)


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
def weekly_report_detail(request, pk):
    report = get_object_or_404(
        WeeklyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related('attachments'),
        pk=pk,
    )
    if not can_view_user_weekly_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo tuần này.')
        return redirect('reports:hub')
    if not weekly_report_visible_to_team(report) and report.employee_id != request.user.id:
        messages.info(request, 'Nhân viên chưa lưu nháp hoặc gửi báo cáo tuần.')
        return redirect(f'{reverse("reports:team_weekly")}?week={report.week_start.isoformat()}')

    can_review = can_review_user_weekly_report(request.user, report)

    if request.method == 'POST' and can_review:
        report.hod_reviewed = request.POST.get('hod_reviewed') == 'on'
        report.hod_note = request.POST.get('hod_note', '').strip()
        report.save()
        messages.success(request, 'Đã cập nhật phản hồi.')
        return redirect('reports:weekly_detail', pk=pk)

    images, files = _weekly_attachments(report)
    profile = report.employee.profile
    edit_report_url = ''
    if report.employee_id == request.user.id and can_submit_daily_report(request.user):
        edit_report_url = f"{reverse('reports:weekly')}?week={report.week_start.isoformat()}"
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
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
        'edit_report_url': edit_report_url,
        'report_period': 'weekly',
        'report_date': report.week_start,
        'week_start': report.week_start,
    })


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
    as_attachment = content_type not in inline_types
    file_handle = open_weekly_attachment(att)
    response = FileResponse(file_handle, content_type=content_type, as_attachment=as_attachment)
    if as_attachment:
        response['Content-Disposition'] = f'attachment; filename="{att.display_name}"'
    return response
