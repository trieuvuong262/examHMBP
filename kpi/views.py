from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from PortalJustPlay.list_search import apply_combined_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import module_perm_required
from hrm.concurrent_positions import effective_roles, user_is_director
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import (
    MODULE_KPI,
    user_can_create_module,
    user_can_delete_module,
    user_can_update_module,
)
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_EMPLOYEE,
    SUBORDINATE_MANAGER_ROLES,
    can_manage_kpi_for_others,
    format_direct_managers_label,
    get_profile,
    get_report_team_users,
    is_global_report_viewer,
    primary_direct_manager,
)

from .models import MonthlyKpi, MonthlyKpiItem
from .services.inline_images import (
    can_view_kpi_inline_image,
    sanitize_actual_html,
    save_kpi_inline_image,
)
from .services.monthly_import import (
    KpiImportError,
    build_monthly_kpi_sample_xlsx,
    parse_monthly_kpi_workbook,
)
from reports.daily_inline_images import inline_image_exists, is_inline_image_relpath, open_inline_image
from reports.nas_health import mark_storage_unavailable

import logging
import mimetypes
import os

logger = logging.getLogger(__name__)

_KPI_IMAGE_TYPES = frozenset({
    'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/png', 'image/gif', 'image/webp',
    'image/bmp', 'image/x-ms-bmp', 'image/x-png',
})
_KPI_IMAGE_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'})
_KPI_IMAGE_MAX_BYTES = 5 * 1024 * 1024


def _kpi_detail_roles(user, kpi_board: MonthlyKpi):
    is_owner = user == kpi_board.employee
    is_manager = user == kpi_board.direct_manager
    if effective_roles(user) & SUBORDINATE_MANAGER_ROLES:
        is_manager = is_manager or get_report_team_users(user).filter(
            pk=kpi_board.employee_id,
        ).exists()
    can_view = (
        is_owner
        or is_manager
        or user.is_superuser
        or ROLE_DIRECTOR in effective_roles(user)
        or is_global_report_viewer(user)
    )
    return is_owner, is_manager, can_view


def _sync_board_direct_manager(board: MonthlyKpi) -> MonthlyKpi:
    """Gắn QL theo Nhân sự (không dùng người import)."""
    primary = primary_direct_manager(board.employee)
    new_id = primary.pk if primary else None
    if board.direct_manager_id != new_id:
        board.direct_manager = primary
        board.save(update_fields=['direct_manager', 'updated_at'])
    return board


def _annotate_boards(boards):
    """Gắn total_score / result / nhãn QL (Nhân sự) lên từng board."""
    for board in boards:
        board.display_total = board.total_score()
        board.display_result = board.result_label()
        board.display_result_code = board.result_code()
        board.has_self = board.self_scored()
        board.has_mgr = board.manager_scored()
        board.hr_manager_label = format_direct_managers_label(board.employee)
        if not board.hr_manager_label and board.direct_manager_id:
            profile = get_profile(board.direct_manager)
            board.hr_manager_label = (
                profile.full_name if profile and profile.full_name
                else board.direct_manager.username
            )
    return boards


def _kpi_perm_context(user) -> dict:
    can_update = user_can_update_module(user, MODULE_KPI)
    can_create = user_can_create_module(user, MODULE_KPI)
    can_delete = user_can_delete_module(user, MODULE_KPI)
    return {
        'can_update': can_update,
        'can_create': can_create,
        'can_delete': can_delete,
        'can_manage_kpi': can_manage_kpi_for_others(user),
    }


def _can_edit_kpi_board(user, board: MonthlyKpi) -> bool:
    if not (user_can_create_module(user, MODULE_KPI) or user_can_update_module(user, MODULE_KPI)):
        return False
    return user.is_superuser or _can_manage_employee(user, board.employee)


def _can_delete_kpi_board(user, board: MonthlyKpi) -> bool:
    if board.employee_id == user.pk and user_can_create_module(user, MODULE_KPI):
        return True
    if not user_can_delete_module(user, MODULE_KPI):
        return False
    return user.is_superuser or _can_manage_employee(user, board.employee)


def _can_manage_employee(user, employee: User) -> bool:
    if user.is_superuser or user_is_director(user) or is_global_report_viewer(user):
        return True
    if employee.pk == user.pk:
        return True  # được giao KPI cho chính mình
    if not (effective_roles(user) & SUBORDINATE_MANAGER_ROLES):
        return False
    return get_report_team_users(user).filter(pk=employee.pk).exists()


def _target_employees_for(user, *, scope: str = 'team'):
    if scope == 'self':
        return User.objects.filter(pk=user.pk).select_related('profile')
    if user_is_director(user) or user.is_superuser or is_global_report_viewer(user):
        return User.objects.filter(is_active=True).exclude(pk=user.pk).select_related('profile')
    if effective_roles(user) & SUBORDINATE_MANAGER_ROLES:
        return get_report_team_users(user).select_related('profile')
    return User.objects.none()


def _parse_month_year(request, *, default_now=True):
    now = timezone.localdate()
    try:
        year = int(request.GET.get('year') or request.POST.get('year') or (now.year if default_now else 0))
    except (TypeError, ValueError):
        year = now.year if default_now else 0
    try:
        month = int(request.GET.get('month') or request.POST.get('month') or (now.month if default_now else 0))
    except (TypeError, ValueError):
        month = now.month if default_now else 0
    if year < 2000 or year > 2100:
        year = now.year
    if month < 1 or month > 12:
        month = now.month
    return year, month


def _annotate_items_for_table(items: list[MonthlyKpiItem]) -> list[MonthlyKpiItem]:
    """Gắn rowspan nhóm + điểm thành phần để render bảng giống Excel."""
    i = 0
    n = len(items)
    while i < n:
        group = (items[i].work_group or '').strip()
        span = 1
        while i + span < n and (items[i + span].work_group or '').strip() == group:
            span += 1
        for j in range(span):
            items[i + j].group_rowspan = span if j == 0 else 0
            items[i + j].display_component = items[i + j].component_score()
            items[i + j].display_effective = items[i + j].effective_score()
        i += span
    return items


def _visible_boards_qs(user, year: int, month: int):
    """Bảng KPI tháng mà user được xem (cá nhân + team / toàn bộ nếu GD / admin+ductn)."""
    item_prefetch = Prefetch('items', queryset=MonthlyKpiItem.objects.order_by('sort_order', 'id'))
    base = MonthlyKpi.objects.filter(year=year, month=month).select_related(
        'employee__profile',
        'direct_manager__profile',
    ).prefetch_related(item_prefetch)

    if user_is_director(user) or user.is_superuser or is_global_report_viewer(user):
        return base.order_by('employee__profile__full_name', 'employee__username')
    if effective_roles(user) & SUBORDINATE_MANAGER_ROLES:
        subordinate_ids = list(get_report_team_users(user).values_list('pk', flat=True))
        return base.filter(
            Q(employee=user)
            | Q(direct_manager=user)
            | Q(employee_id__in=subordinate_ids),
        ).order_by('employee__profile__full_name', 'employee__username')
    return base.filter(employee=user).order_by('-year', '-month')


@module_perm_required(MODULE_KPI, 'view')
def kpi_list_view(request):
    search_query = get_search_query(request)
    year, month = _parse_month_year(request)
    item_prefetch = Prefetch('items', queryset=MonthlyKpiItem.objects.order_by('sort_order', 'id'))

    base = MonthlyKpi.objects.filter(year=year, month=month).select_related(
        'employee__profile',
        'direct_manager__profile',
    ).prefetch_related(item_prefetch)

    my_kpis_qs = base.filter(employee=request.user).order_by('-year', '-month')

    if user_is_director(request.user) or request.user.is_superuser or is_global_report_viewer(request.user):
        team_kpis_qs = base.exclude(employee=request.user).order_by('employee__profile__full_name', 'employee__username')
    elif effective_roles(request.user) & SUBORDINATE_MANAGER_ROLES:
        subordinate_ids = list(get_report_team_users(request.user).values_list('pk', flat=True))
        team_kpis_qs = base.filter(
            Q(direct_manager=request.user) | Q(employee_id__in=subordinate_ids),
        ).exclude(employee=request.user).order_by('employee__profile__full_name', 'employee__username')
    else:
        team_kpis_qs = MonthlyKpi.objects.none()

    def _kpi_search(qs):
        if not search_query:
            return qs
        return apply_combined_search(qs, search_query, lambda term: (
            Q(employee__username__icontains=term)
            | Q(employee__first_name__icontains=term)
            | Q(employee__last_name__icontains=term)
            | Q(employee__email__icontains=term)
            | Q(employee__profile__full_name__icontains=term)
            | Q(employee__profile__employee_code__icontains=term)
            | Q(direct_manager__username__icontains=term)
            | Q(direct_manager__profile__full_name__icontains=term)
        ))

    my_kpis_qs = _kpi_search(my_kpis_qs)
    team_kpis_qs = _kpi_search(team_kpis_qs)

    my_page, my_query_string = paginate_queryset(request, my_kpis_qs, page_param='my_page')
    team_page, team_query_string = paginate_queryset(request, team_kpis_qs, page_param='team_page')

    my_list = _annotate_boards(list(my_page.object_list))
    team_list = _annotate_boards(list(team_page.object_list))
    for board in my_list:
        board.can_edit_board = _can_edit_kpi_board(request.user, board)
        board.can_delete_board = _can_delete_kpi_board(request.user, board)

    years = list(range(timezone.localdate().year + 1, timezone.localdate().year - 5, -1))
    show_subordinate_kpi = (
        request.user.is_superuser
        or user_is_director(request.user)
        or is_global_report_viewer(request.user)
        or bool(effective_roles(request.user) & SUBORDINATE_MANAGER_ROLES)
    )
    can_import_team = show_subordinate_kpi or can_manage_kpi_for_others(request.user)
    perm_ctx = _kpi_perm_context(request.user)
    has_my_kpi_this_month = base.filter(employee=request.user).exists()
    can_create_self_kpi = perm_ctx['can_create'] and not has_my_kpi_this_month

    return render(request, 'kpi/kpi_list.html', {
        'my_kpis': my_list,
        'my_page': my_page,
        'my_query_string': my_query_string,
        'team_kpis': team_list,
        'team_page': team_page,
        'team_query_string': team_query_string,
        'search_query': search_query,
        'filter_year': year,
        'filter_month': month,
        'year_choices': years,
        'month_choices': list(range(1, 13)),
        'show_subordinate_kpi': show_subordinate_kpi,
        'can_import_team': can_import_team,
        'can_create_self_kpi': can_create_self_kpi,
        'can_view_summary': user_can_access_menu(request.user, MODULE_KPI, 'summary'),
        **perm_ctx,
    })


@module_perm_required(MODULE_KPI, 'view')
def kpi_summary_view(request):
    if not user_can_access_menu(request.user, MODULE_KPI, 'summary'):
        messages.error(request, 'Bạn không có quyền xem tổng kết KPI.')
        return redirect('kpi_list')

    search_query = get_search_query(request)
    year, month = _parse_month_year(request)
    boards_qs = _visible_boards_qs(request.user, year, month)

    if search_query:
        boards_qs = apply_combined_search(boards_qs, search_query, lambda term: (
            Q(employee__username__icontains=term)
            | Q(employee__first_name__icontains=term)
            | Q(employee__last_name__icontains=term)
            | Q(employee__email__icontains=term)
            | Q(employee__profile__full_name__icontains=term)
            | Q(employee__profile__employee_code__icontains=term)
            | Q(direct_manager__username__icontains=term)
            | Q(direct_manager__profile__full_name__icontains=term)
        ))

    page_obj, query_string = paginate_queryset(request, boards_qs, page_param='page')
    boards = _annotate_boards(list(page_obj.object_list))

    # Thống kê trên toàn bộ kết quả lọc (không chỉ trang hiện tại)
    all_boards = _annotate_boards(list(boards_qs))
    counts = {
        'total': len(all_boards),
        'pending': 0,
        'fail': 0,
        'pass': 0,
        'exceed': 0,
        'self_done': 0,
        'mgr_done': 0,
    }
    scored_totals = []
    for board in all_boards:
        code = board.display_result_code
        if code in counts:
            counts[code] += 1
        if board.has_self:
            counts['self_done'] += 1
        if board.has_mgr:
            counts['mgr_done'] += 1
        if board.display_total is not None:
            scored_totals.append(board.display_total)
    avg_score = round(sum(scored_totals) / len(scored_totals), 2) if scored_totals else None

    years = list(range(timezone.localdate().year + 1, timezone.localdate().year - 5, -1))
    return render(request, 'kpi/kpi_summary.html', {
        'boards': boards,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'filter_year': year,
        'filter_month': month,
        'year_choices': years,
        'month_choices': list(range(1, 13)),
        'counts': counts,
        'avg_score': avg_score,
        **_kpi_perm_context(request.user),
    })


@module_perm_required(MODULE_KPI, 'view')
def kpi_detail_view(request, kpi_id):
    kpi_board = get_object_or_404(
        MonthlyKpi.objects.select_related('employee__profile', 'direct_manager__profile'),
        pk=kpi_id,
    )
    items = list(kpi_board.items.all().order_by('sort_order', 'id'))

    is_owner, is_manager, can_view_board = _kpi_detail_roles(request.user, kpi_board)
    if not can_view_board:
        messages.error(request, 'Bạn không có quyền xem bảng KPI này.')
        return redirect('kpi_list')

    _sync_board_direct_manager(kpi_board)
    hr_manager_label = format_direct_managers_label(kpi_board.employee)
    if not hr_manager_label and kpi_board.direct_manager_id:
        mgr_profile = get_profile(kpi_board.direct_manager)
        hr_manager_label = (
            mgr_profile.full_name if mgr_profile and mgr_profile.full_name
            else kpi_board.direct_manager.username
        )

    perm = _kpi_perm_context(request.user)
    can_update = perm['can_update']
    # Owner luôn được tự chấm (đã qua quyền view module); QL / giám đốc chấm cột QL.
    can_edit_self = is_owner
    can_edit_manager = is_manager
    if (request.user.is_superuser or ROLE_DIRECTOR in effective_roles(request.user)) and not is_owner:
        can_edit_manager = True

    if request.method == 'POST':
        if not can_edit_self and not can_edit_manager:
            messages.error(request, 'Bạn không có quyền sửa / chấm điểm KPI.')
            return redirect('kpi_detail', kpi_id=kpi_id)

        for item in items:
            prefix = f'item_{item.id}_'
            try:
                if can_edit_self:
                    if f'{prefix}self_actual' in request.POST:
                        item.self_actual = sanitize_actual_html(
                            request.POST.get(f'{prefix}self_actual') or '',
                        )
                    raw_self = request.POST.get(f'{prefix}self_score')
                    if raw_self is not None:
                        item.self_score = float(raw_self) if str(raw_self).strip() != '' else None
                if can_edit_manager:
                    if f'{prefix}mgr_actual' in request.POST:
                        item.mgr_actual = sanitize_actual_html(
                            request.POST.get(f'{prefix}mgr_actual') or '',
                        )
                    raw_mgr = request.POST.get(f'{prefix}mgr_score')
                    if raw_mgr is not None:
                        item.mgr_score = float(raw_mgr) if str(raw_mgr).strip() != '' else None
                item.save()
            except ValueError:
                messages.warning(request, f'Định dạng điểm không hợp lệ tại: {item.indicator[:60]}')
                continue

        messages.success(request, 'Đã lưu đánh giá KPI.')
        return redirect('kpi_detail', kpi_id=kpi_id)

    items = _annotate_items_for_table(items)
    total = kpi_board.total_score()
    return render(request, 'kpi/kpi_detail.html', {
        'kpi': kpi_board,
        'items': items,
        'is_owner': is_owner,
        'is_manager': is_manager,
        'can_update': can_update,
        'can_edit_self': can_edit_self,
        'can_edit_manager': can_edit_manager,
        'total_score': total,
        'result_label': kpi_board.result_label(),
        'result_code': kpi_board.result_code(),
        'hr_manager_label': hr_manager_label,
        'kpi_image_upload_url': reverse('kpi_inline_upload', kwargs={'kpi_id': kpi_board.pk}),
        **perm,
    })


def _kpi_upload_error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({'uploaded': 0, 'error': {'message': message}}, status=status)


def _is_allowed_kpi_image(upload) -> bool:
    content_type = (getattr(upload, 'content_type', '') or '').split(';')[0].strip().lower()
    if content_type in _KPI_IMAGE_TYPES:
        return True
    if content_type in ('', 'application/octet-stream'):
        ext = os.path.splitext(getattr(upload, 'name', '') or '')[1].lower()
        return ext in _KPI_IMAGE_EXTS or not ext
    return False


@module_perm_required(MODULE_KPI, 'view')
@require_POST
def kpi_inline_upload(request, kpi_id):
    kpi_board = get_object_or_404(MonthlyKpi, pk=kpi_id)
    is_owner, is_manager, can_view_board = _kpi_detail_roles(request.user, kpi_board)
    if not can_view_board:
        return _kpi_upload_error('Không có quyền.', status=403)
    can_edit_self = is_owner
    can_edit_manager = is_manager
    if (request.user.is_superuser or ROLE_DIRECTOR in effective_roles(request.user)) and not is_owner:
        can_edit_manager = True
    if not can_edit_self and not can_edit_manager:
        return _kpi_upload_error('Không có quyền chèn ảnh.', status=403)

    upload = request.FILES.get('upload') or request.FILES.get('file')
    if not upload:
        return _kpi_upload_error('Không có file.')
    if not _is_allowed_kpi_image(upload):
        return _kpi_upload_error('File không hợp lệ.')
    if upload.size > _KPI_IMAGE_MAX_BYTES:
        return _kpi_upload_error('Ảnh quá lớn (tối đa 5MB).')

    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext not in _KPI_IMAGE_EXTS:
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
        rel_path = save_kpi_inline_image(
            upload,
            username=request.user.username,
            year=kpi_board.year,
            month=kpi_board.month,
            ext=ext,
        )
    except OSError as exc:
        logger.exception('KPI image upload failed for %s: %s', request.user.username, exc)
        mark_storage_unavailable()
        return _kpi_upload_error('Không lưu được ảnh. Vui lòng thử lại.', status=503)

    url = request.build_absolute_uri(
        reverse('kpi_inline_image', kwargs={'relpath': rel_path}),
    )
    return JsonResponse({
        'uploaded': 1,
        'fileName': os.path.basename(rel_path),
        'url': url,
    })


@module_perm_required(MODULE_KPI, 'view')
def kpi_inline_image_serve(request, relpath):
    rel = (relpath or '').lstrip('/')
    if not is_inline_image_relpath(rel):
        return HttpResponse(status=404)
    if not can_view_kpi_inline_image(request.user, rel):
        return HttpResponse(status=403)
    if not inline_image_exists(rel):
        return HttpResponse(status=404)
    content_type = mimetypes.guess_type(rel)[0] or 'application/octet-stream'
    return FileResponse(open_inline_image(rel), content_type=content_type)


def _resolve_edit_board(request, scope: str):
    raw = request.POST.get('edit_id') or request.GET.get('edit') or ''
    try:
        edit_id = int(raw)
    except (TypeError, ValueError):
        return None
    board = MonthlyKpi.objects.filter(pk=edit_id).select_related('employee').first()
    if not board or not _can_edit_kpi_board(request.user, board):
        return None
    if scope == 'self' and board.employee_id != request.user.pk:
        return None
    if scope == 'team' and board.employee_id == request.user.pk:
        return None
    return board


@module_perm_required(MODULE_KPI, 'create')
def kpi_import_excel(request):
    profile = get_profile(request.user)
    if not profile:
        messages.error(request, 'Tài khoản chưa có hồ sơ nhân sự. Vui lòng liên hệ HR/IT.')
        return redirect('kpi_list')

    scope = (request.GET.get('scope') or request.POST.get('scope') or 'team').strip().lower()
    if scope not in ('self', 'team'):
        scope = 'team'

    can_import_team = (
        request.user.is_superuser
        or user_is_director(request.user)
        or is_global_report_viewer(request.user)
        or bool(effective_roles(request.user) & SUBORDINATE_MANAGER_ROLES)
        or can_manage_kpi_for_others(request.user)
    )
    if scope == 'team' and not can_import_team:
        messages.error(request, 'Chỉ quản lý mới được giao KPI cho team.')
        return redirect('kpi_list')

    edit_board = _resolve_edit_board(request, scope)
    if (request.GET.get('edit') or request.POST.get('edit_id')) and not edit_board:
        messages.error(request, 'Không tìm thấy bảng KPI để sửa hoặc bạn không có quyền.')
        return redirect('kpi_list')

    target_employees = _target_employees_for(request.user, scope=scope)
    now = timezone.localdate()
    year_choices = list(range(now.year + 1, now.year - 5, -1))
    if edit_board:
        default_year, default_month = edit_board.year, edit_board.month
    else:
        default_year, default_month = _parse_month_year(request)

    if scope == 'self' and request.method == 'GET' and not edit_board:
        if MonthlyKpi.objects.filter(
            employee=request.user, year=default_year, month=default_month,
        ).exists():
            messages.info(
                request,
                f'Bạn đã có KPI tháng {default_month:02d}/{default_year}. '
                'Chỉ tạo thêm vào tháng sau.',
            )
            return redirect(
                f"{reverse('kpi_list')}?month={default_month}&year={default_year}"
            )

    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        if edit_board:
            employee = edit_board.employee
            year, month = edit_board.year, edit_board.month
        else:
            if scope == 'self':
                employee_id = request.user.pk
            else:
                employee_id = request.POST.get('employee_id')
            try:
                year = int(request.POST.get('year') or default_year)
                month = int(request.POST.get('month') or default_month)
            except (TypeError, ValueError):
                messages.error(request, 'Tháng / năm không hợp lệ.')
                return redirect(f"{reverse('kpi_import_excel')}?scope={scope}")

            if month < 1 or month > 12 or year < 2000:
                messages.error(request, 'Tháng / năm không hợp lệ.')
                return redirect(f"{reverse('kpi_import_excel')}?scope={scope}")

            employee = User.objects.filter(pk=employee_id, is_active=True).first()
            if not employee:
                messages.error(request, 'Vui lòng chọn nhân viên.')
                return redirect(f"{reverse('kpi_import_excel')}?scope={scope}")
            if scope == 'self' and employee.pk != request.user.pk:
                messages.error(request, 'Chỉ được giao KPI cho chính bạn ở mục này.')
                return redirect(f"{reverse('kpi_import_excel')}?scope=self")
            if scope == 'team' and employee.pk == request.user.pk:
                messages.error(request, 'Giao KPI cá nhân dùng nút ở mục «KPI của tôi».')
                return redirect(f"{reverse('kpi_import_excel')}?scope=team")
            if not _can_manage_employee(request.user, employee) and not request.user.is_superuser:
                messages.error(request, 'Bạn không có quyền giao KPI cho nhân viên này.')
                return redirect(f"{reverse('kpi_import_excel')}?scope={scope}")

            if scope == 'self' and MonthlyKpi.objects.filter(
                employee=employee, year=year, month=month,
            ).exists():
                messages.error(
                    request,
                    f'Bạn đã có KPI tháng {month:02d}/{year}. Chỉ tạo thêm vào tháng sau.',
                )
                return redirect(f"{reverse('kpi_list')}?month={month}&year={year}")

        redirect_qs = f"scope={scope}&month={month}&year={year}"
        if edit_board:
            redirect_qs += f"&edit={edit_board.pk}"

        if not excel_file or not excel_file.name.lower().endswith(('.xlsx', '.xlsm')):
            messages.error(request, 'Vui lòng chọn file Excel .xlsx.')
            return redirect(f"{reverse('kpi_import_excel')}?{redirect_qs}")

        try:
            parsed = parse_monthly_kpi_workbook(excel_file)
        except KpiImportError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('kpi_import_excel')}?{redirect_qs}")

        with transaction.atomic():
            defaults = {
                'imported_by': request.user,
                'imported_at': timezone.now(),
                'direct_manager': primary_direct_manager(employee),
            }
            board, created = MonthlyKpi.objects.update_or_create(
                employee=employee,
                year=year,
                month=month,
                defaults=defaults,
            )
            _sync_board_direct_manager(board)
            board.items.all().delete()
            MonthlyKpiItem.objects.bulk_create([
                MonthlyKpiItem(
                    monthly_kpi=board,
                    sort_order=row.sort_order,
                    work_group=row.work_group,
                    weightage=row.weightage,
                    indicator=row.indicator,
                    level_fail=row.level_fail,
                    level_pass=row.level_pass,
                    level_exceed=row.level_exceed,
                )
                for row in parsed.rows
            ])

        action = 'cập nhật' if edit_board or not created else 'giao'
        messages.success(
            request,
            f'Đã {action} KPI tháng {month:02d}/{year} cho {employee.get_username()} '
            f'({len(parsed.rows)} tiêu chí).',
        )
        return redirect('kpi_detail', kpi_id=board.pk)

    return render(request, 'kpi/kpi_import.html', {
        'scope': scope,
        'edit_board': edit_board,
        'target_employees': target_employees,
        'fixed_employee': (
            edit_board.employee if edit_board
            else (request.user if scope == 'self' else None)
        ),
        'year_choices': year_choices,
        'month_choices': list(range(1, 13)),
        'default_year': default_year,
        'default_month': default_month,
        'period_locked': bool(edit_board),
        **_kpi_perm_context(request.user),
    })


@module_perm_required(MODULE_KPI, 'view')
@require_POST
def kpi_delete_view(request, kpi_id):
    board = get_object_or_404(MonthlyKpi.objects.select_related('employee'), pk=kpi_id)
    if not _can_delete_kpi_board(request.user, board):
        messages.error(request, 'Bạn không có quyền xóa bảng KPI này.')
        return redirect('kpi_list')
    month, year = board.month, board.year
    label = board.employee.get_username()
    board.delete()
    messages.success(request, f'Đã xóa KPI tháng {month:02d}/{year} của {label}.')
    return redirect(f"{reverse('kpi_list')}?month={month}&year={year}")


@module_perm_required(MODULE_KPI, 'create')
def download_kpi_sample_excel(request):
    content = build_monthly_kpi_sample_xlsx()
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename=Mau_Import_KPI_Thang.xlsx'
    return response
