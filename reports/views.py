import os
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
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
    get_report_profile,
    is_production_report_user,
)

from reports.week_utils import monday_of, parse_week_start, week_end, week_label

from .forms import (
    DailyWorkReportForm,
    DailyWorkReportLineFormSet,
    OfficeDailyWorkReportForm,
    WeeklyWorkReportForm,
)
from .models import DailyWorkReport, WeeklyWorkReport
from .team_utils import (
    build_report_team_department_groups,
    daily_report_visible_to_team,
    department_filter_choices,
    meaningful_daily_reports_qs,
    meaningful_weekly_reports_qs,
    weekly_report_visible_to_team,
)
from .weekly_uploads import copy_weekly_attachments, save_weekly_uploads, weekly_report_has_content


_CK5_IMAGE_TYPES = frozenset({'image/jpeg', 'image/png', 'image/gif', 'image/webp'})
_CK5_IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp'})
_CK5_MAX_BYTES = 5 * 1024 * 1024


def _reports_access_required(view_func):
    return module_perm_required(MODULE_REPORTS, 'view')(view_func)


_WEEKLY_SUBMIT_VIEWS = frozenset({'weekly_report', 'copy_prev_week'})


def _require_submit_access(view_func):
    @module_perm_required(MODULE_REPORTS, 'create')
    def wrapper(request, *args, **kwargs):
        if not can_submit_daily_report(request.user):
            if can_view_team_reports(request.user):
                if view_func.__name__ in _WEEKLY_SUBMIT_VIEWS:
                    return redirect('reports:team_weekly')
                return redirect('reports:team')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@_reports_access_required
def report_hub(request):
    if can_view_team_reports(request.user) and is_director(request.user):
        return redirect('reports:team')
    if can_submit_daily_report(request.user):
        return redirect('reports:today')
    if can_view_team_reports(request.user):
        return redirect('reports:team')
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


def _daily_report_defaults(user):
    profile = get_report_profile(user)
    return {
        'shift': DailyWorkReport.SHIFT_MORNING if profile == REPORT_PROFILE_PRODUCTION else '',
        'report_profile': profile,
        'status': DailyWorkReport.STATUS_DRAFT,
    }


def _load_daily_report(user, report_date):
    """Chỉ lấy bản ghi đã lưu; không tạo mới khi mở trang."""
    try:
        report = DailyWorkReport.objects.get(employee=user, report_date=report_date)
    except DailyWorkReport.DoesNotExist:
        report = DailyWorkReport(employee=user, report_date=report_date, **_daily_report_defaults(user))
        return report
    profile = get_report_profile(user)
    if report.report_profile != profile:
        report.report_profile = profile
    return report


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
    report = _load_daily_report(request.user, report_date)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        report = _ensure_daily_report_saved(report)
        form = DailyWorkReportForm(request.POST, instance=report)
        formset = DailyWorkReportLineFormSet(request.POST, instance=report)
        if form.is_valid() and formset.is_valid():
            report = form.save(commit=False)
            report.report_profile = REPORT_PROFILE_PRODUCTION
            messages.success(request, _finalize_report_submission(report, action))
            report.save()
            formset.save()
            return redirect('reports:today')
    else:
        form = DailyWorkReportForm(instance=report)
        formset = DailyWorkReportLineFormSet(instance=report if report.pk else None)

    ctx = _report_context_common(request, report_date)
    ctx.update({
        'form': form,
        'formset': formset,
        'report': report,
        'report_period': 'daily',
        'copy_url': reverse('reports:copy_yesterday') if ctx['has_yesterday'] else None,
        'copy_label': 'Sao chép HQ',
        'copy_confirm': 'Sao chép nội dung từ hôm qua?',
    })
    return render(request, 'reports/today.html', ctx)


def _today_office_report(request, report_date):
    from hrm.permissions import get_profile as load_profile
    user_profile = load_profile(request.user)

    report = _load_daily_report(request.user, report_date)

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
            return redirect('reports:today')
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
        'copy_url': reverse('reports:copy_yesterday') if ctx['has_yesterday'] else None,
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


@_require_submit_access
def today_report(request):
    report_date = _parse_report_date(request)
    if is_production_report_user(request.user):
        return _today_production_report(request, report_date)
    return _today_office_report(request, report_date)


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
def copy_yesterday(request):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    source = DailyWorkReport.objects.filter(
        employee=request.user, report_date=yesterday,
    ).prefetch_related('lines').first()
    if not source:
        messages.warning(request, 'Không có báo cáo hôm qua để sao chép.')
        return redirect('reports:today')

    profile = get_report_profile(request.user)
    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=today,
        defaults={
            'shift': source.shift if profile == REPORT_PROFILE_PRODUCTION else '',
            'report_profile': profile,
            'status': DailyWorkReport.STATUS_DRAFT,
        },
    )
    report.report_profile = profile
    report.shift = source.shift if profile == REPORT_PROFILE_PRODUCTION else ''
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    report.draft_saved_at = None
    if profile == REPORT_PROFILE_OFFICE:
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
    return redirect('reports:today')


@_require_submit_access
def my_reports(request):
    search_query = get_search_query(request)
    reports_qs = DailyWorkReport.objects.filter(
        employee=request.user,
    ).annotate(line_count=Count('lines'), total_qty=Sum('lines__quantity')).order_by('-report_date')
    reports_qs = apply_combined_search(reports_qs, search_query, lambda term: (
        Q(hod_note__icontains=term)
        | Q(status__icontains=term)
        | Q(shift__icontains=term)
        | Q(lines__area__icontains=term)
        | Q(lines__order_code__icontains=term)
        | Q(lines__product_name__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, reports_qs)
    return render(request, 'reports/my_reports.html', {
        'reports': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_view_team': can_view_team_reports(request.user),
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


@_reports_access_required
def team_reports(request):
    if not can_view_team_reports(request.user):
        messages.error(
            request,
            'Chưa có nhân viên cấp dưới trực tiếp. HR cần cấu hình tại Nhân sự → Sửa nhân viên → Nhân viên dưới quyền.',
        )
        if can_submit_daily_report(request.user):
            return redirect('reports:today')
        return redirect('home_portal')

    report_date = request.GET.get('date') or timezone.localdate()
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    search_query = get_search_query(request)
    dept_filter = (request.GET.get('dept') or '').strip()
    team = _team_queryset(request.user, search_query)
    all_team_ids = list(team.values_list('id', flat=True))
    all_reports = meaningful_daily_reports_qs().filter(
        employee_id__in=all_team_ids,
        report_date=report_date,
    )
    team_count = team.count()
    submitted = all_reports.filter(status=DailyWorkReport.STATUS_SUBMITTED).count()
    missing = team_count - submitted

    reports = meaningful_daily_reports_qs().filter(
        employee_id__in=all_team_ids,
        report_date=report_date,
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

    return render(request, 'reports/team.html', {
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'selected_dept': dept_filter,
        'search_query': search_query,
        'report_date': report_date,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
        'report_period': 'daily',
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

    ctx = _weekly_context_common(request, week_start)
    ctx.update({
        'department_groups': department_groups,
        'dept_choices': dept_choices,
        'selected_dept': dept_filter,
        'search_query': search_query,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
        'report_period': 'weekly',
    })
    return render(request, 'reports/team_weekly.html', ctx)


@_reports_access_required
def report_detail(request, pk):
    report = get_object_or_404(
        DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related('lines'),
        pk=pk,
    )
    if not can_view_user_report(request.user, report):
        messages.error(request, 'Bạn không có quyền xem báo cáo này.')
        return redirect('reports:hub')

    can_review = can_review_user_report(request.user, report)

    if request.method == 'POST' and can_review:
        report.hod_reviewed = request.POST.get('hod_reviewed') == 'on'
        report.hod_note = request.POST.get('hod_note', '').strip()
        report.save()
        messages.success(request, 'Đã cập nhật phản hồi.')
        return redirect('reports:detail', pk=pk)

    from reports.office_content import normalize_spreadsheet_json

    office_sheet = normalize_spreadsheet_json(report.spreadsheet_json)
    return render(request, 'reports/detail.html', {
        'report': report,
        'office_sheet': office_sheet,
        'can_review': can_review,
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
    })


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
    return render(request, 'reports/weekly_detail.html', {
        'report': report,
        'weekly_images': images,
        'weekly_files': files,
        'week_label': week_label(report.week_start),
        'can_review': can_review,
        'can_submit_report': can_submit_daily_report(request.user),
        'can_view_team': can_view_team_reports(request.user),
    })
