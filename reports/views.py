from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib import messages

from hrm.permissions import can_view_team_reports, get_report_team_users, is_gm, is_hod, is_portal_admin
from PortalJustPlay.pagination import paginate_queryset

from .forms import DailyWorkReportForm, DailyWorkReportLineFormSet
from .models import DailyWorkReport


def _is_hod_or_above(user):
    return can_view_team_reports(user)


def _team_users(viewer):
    return get_report_team_users(viewer)


@login_required
def report_hub(request):
    if _is_hod_or_above(request.user):
        return redirect('reports:team')
    return redirect('reports:today')


@login_required
def today_report(request):
    report_date = request.GET.get('date') or timezone.localdate()
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=report_date,
        defaults={'shift': DailyWorkReport.SHIFT_MORNING},
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form = DailyWorkReportForm(request.POST, instance=report)
        formset = DailyWorkReportLineFormSet(request.POST, instance=report)
        if form.is_valid() and formset.is_valid():
            report = form.save(commit=False)
            if action == 'submit':
                report.status = DailyWorkReport.STATUS_SUBMITTED
                report.submitted_at = timezone.now()
                messages.success(request, 'Đã nộp báo cáo cho HOD.')
            else:
                report.status = DailyWorkReport.STATUS_DRAFT
                messages.success(request, 'Đã lưu nháp báo cáo.')
            report.save()
            formset.save()
            return redirect('reports:today')
    else:
        form = DailyWorkReportForm(instance=report)
        formset = DailyWorkReportLineFormSet(instance=report)

    yesterday = report_date - timedelta(days=1)
    has_yesterday = DailyWorkReport.objects.filter(
        employee=request.user,
        report_date=yesterday,
    ).exists()

    return render(request, 'reports/today.html', {
        'form': form,
        'formset': formset,
        'report': report,
        'has_yesterday': has_yesterday,
        'yesterday': yesterday,
    })


@login_required
def copy_yesterday(request):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    source = DailyWorkReport.objects.filter(employee=request.user, report_date=yesterday).prefetch_related('lines').first()
    if not source:
        messages.warning(request, 'Không có báo cáo hôm qua để sao chép.')
        return redirect('reports:today')

    report, _ = DailyWorkReport.objects.get_or_create(
        employee=request.user,
        report_date=today,
        defaults={'shift': source.shift, 'status': DailyWorkReport.STATUS_DRAFT},
    )
    report.shift = source.shift
    report.status = DailyWorkReport.STATUS_DRAFT
    report.submitted_at = None
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


@login_required
def my_reports(request):
    reports_qs = DailyWorkReport.objects.filter(
        employee=request.user,
    ).annotate(line_count=Count('lines'), total_qty=Sum('lines__quantity')).order_by('-report_date')
    page_obj, query_string = paginate_queryset(request, reports_qs)
    return render(request, 'reports/my_reports.html', {
        'reports': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
    })


@login_required
def team_reports(request):
    if not _is_hod_or_above(request.user):
        messages.error(request, 'Chức năng này dành cho HOD/Quản lý.')
        return redirect('reports:today')

    report_date = request.GET.get('date') or timezone.localdate()
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    team = _team_users(request.user).order_by('profile__full_name', 'username')
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
        'report_date': report_date,
        'submitted_count': submitted,
        'missing_count': missing,
        'team_count': team_count,
    })


@login_required
def report_detail(request, pk):
    report = get_object_or_404(
        DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related('lines'),
        pk=pk,
    )
    can_view = (
        report.employee_id == request.user.id
        or _is_hod_or_above(request.user)
        or report.employee_id in _team_users(request.user).values_list('id', flat=True)
    )
    if not can_view:
        messages.error(request, 'Bạn không có quyền xem báo cáo này.')
        return redirect('reports:hub')

    if request.method == 'POST' and _is_hod_or_above(request.user):
        report.hod_reviewed = request.POST.get('hod_reviewed') == 'on'
        report.hod_note = request.POST.get('hod_note', '').strip()
        report.save()
        messages.success(request, 'Đã cập nhật phản hồi HOD.')
        return redirect('reports:detail', pk=pk)

    return render(request, 'reports/detail.html', {
        'report': report,
        'can_review': _is_hod_or_above(request.user) and report.employee_id != request.user.id,
    })
