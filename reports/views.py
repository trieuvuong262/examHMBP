import os
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib import messages
from django.db.models import Count, Sum, Q

from hrm.module_permissions import MODULE_REPORTS, user_can_access_module
from hrm.permissions import (
    can_review_user_report,
    can_submit_daily_report,
    can_view_team_reports,
    can_view_user_report,
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

from .forms import DailyWorkReportForm, DailyWorkReportLineFormSet, OfficeDailyWorkReportForm
from .models import DailyWorkReport


_CK5_IMAGE_TYPES = frozenset({'image/jpeg', 'image/png', 'image/gif', 'image/webp'})
_CK5_IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp'})
_CK5_MAX_BYTES = 5 * 1024 * 1024


def _reports_access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_REPORTS):
            messages.error(request, 'Bạn không có quyền truy cập module Báo cáo.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _require_submit_access(view_func):
    @_reports_access_required
    def wrapper(request, *args, **kwargs):
        if not can_submit_daily_report(request.user):
            messages.info(request, 'Vai trò Giám đốc chỉ xem báo cáo cấp dưới, không nộp báo cáo cá nhân.')
            if can_view_team_reports(request.user):
                return redirect('reports:team')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
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
        'has_yesterday': DailyWorkReport.objects.filter(
            employee=request.user,
            report_date=yesterday,
        ).exists(),
        'yesterday': yesterday,
        'can_view_team': can_view_team_reports(request.user),
    }


def _get_or_create_daily_report(user, report_date):
    profile = get_report_profile(user)
    defaults = {
        'shift': DailyWorkReport.SHIFT_MORNING if profile == REPORT_PROFILE_PRODUCTION else '',
        'report_profile': profile,
    }
    report, created = DailyWorkReport.objects.get_or_create(
        employee=user,
        report_date=report_date,
        defaults=defaults,
    )
    if not created and report.report_profile != profile:
        report.report_profile = profile
        report.save(update_fields=['report_profile', 'updated_at'])
    return report


def _finalize_report_submission(report, action):
    if action == 'submit':
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submitted_at = timezone.now()
        return 'Đã nộp báo cáo cho cấp trên.'
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
    return 'Đã lưu nháp báo cáo.'


def _today_production_report(request, report_date):
    report = _get_or_create_daily_report(request.user, report_date)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
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
        formset = DailyWorkReportLineFormSet(instance=report)

    ctx = _report_context_common(request, report_date)
    ctx.update({'form': form, 'formset': formset, 'report': report})
    return render(request, 'reports/today.html', ctx)


def _today_office_report(request, report_date):
    from hrm.permissions import get_profile as load_profile
    user_profile = load_profile(request.user)

    report = _get_or_create_daily_report(request.user, report_date)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
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
    ctx.update({
        'form': form,
        'report': report,
        'employee_name': (user_profile.full_name if user_profile else '') or request.user.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
    })
    return render(request, 'reports/today_office.html', ctx)


@_require_submit_access
def today_report(request):
    report_date = _parse_report_date(request)
    if is_production_report_user(request.user):
        return _today_production_report(request, report_date)
    return _today_office_report(request, report_date)


@login_required
@require_POST
def ckeditor5_upload(request):
    if not user_can_access_module(request.user, MODULE_REPORTS):
        return JsonResponse({'error': {'message': 'Không có quyền tải ảnh.'}}, status=403)

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
    team = get_report_team_users(request.user)
    team = apply_user_search(team, search_query)
    all_team_ids = list(team.values_list('id', flat=True))
    all_reports = DailyWorkReport.objects.filter(
        employee_id__in=all_team_ids,
        report_date=report_date,
    )
    team_count = team.count()
    submitted = all_reports.filter(status=DailyWorkReport.STATUS_SUBMITTED).count()
    missing = team_count - submitted

    team_page, query_string = paginate_queryset(request, team)
    page_team_ids = list(team_page.object_list.values_list('id', flat=True))
    reports = DailyWorkReport.objects.filter(
        employee_id__in=page_team_ids,
        report_date=report_date,
    ).select_related('employee', 'employee__profile').annotate(
        line_count=Count('lines'),
        total_qty=Sum('lines__quantity'),
    )
    report_map = {r.employee_id: r for r in reports}

    rows = []
    for member in team_page.object_list:
        rows.append({'member': member, 'report': report_map.get(member.id)})

    return render(request, 'reports/team.html', {
        'rows': rows,
        'page_obj': team_page,
        'query_string': query_string,
        'search_query': search_query,
        'report_date': report_date,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
        'can_submit_report': can_submit_daily_report(request.user),
    })


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
