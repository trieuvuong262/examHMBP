from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import (
    STOCKTAKE_STATUS_CLOSED,
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_DRAFT,
    STOCKTAKE_STATUS_LABELS,
)
from kho_npl.services.scrap_warehouse import source_locations_qs
from kho_npl.forms import StocktakeForm, StocktakeLineFormSet
from kho_npl.models import Stocktake, StocktakeLine
from kho_npl.services.doc_numbers import next_stocktake_number
from kho_npl.services.stocktakes import (
    StocktakeWorkflowError,
    close_stocktake,
    populate_stocktake_lines,
    start_stocktake_counting,
    stocktake_can_count,
    stocktake_is_editable,
)
from kho_npl.doc_list_columns import (
    STOCKTAKE_LIST_COLUMNS,
    STOCKTAKE_LIST_SORT_FIELDS,
    STOCKTAKE_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.doc_list_utils import STOCKTAKE_STATUS_FILTER_CHOICES, doc_list_sort, doc_status_filter
from kho_npl.view_utils import nav_context, perm_context


def _stocktake_lines_qs(stocktake):
    return (
        stocktake.lines
        .select_related('material__unit', 'location')
        .order_by('material__code')
    )


def _stocktake_line_count(stocktake):
    return stocktake.lines.count()


STOCKTAKE_WH_PREVIEW = 6


def _parse_warehouse_id(request):
    raw = (request.GET.get('wh') or '').strip()
    if not raw:
        return None
    try:
        wh_id = int(raw)
    except (TypeError, ValueError):
        return None
    return wh_id if wh_id > 0 else None


def _stocktake_filtered_qs(search_query, status):
    qs = Stocktake.objects.select_related('created_by', 'location')
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(location__code__icontains=search_query)
            | Q(location__name__icontains=search_query),
        )
    return qs


def _stocktake_list_columns(*, single_warehouse: bool):
    if single_warehouse:
        return [c for c in STOCKTAKE_LIST_COLUMNS if c['key'] != 'location']
    return STOCKTAKE_LIST_COLUMNS


def _stocktake_list_query_string(*, warehouse_id, status, search_query, sort_key='', sort_dir=''):
    parts = []
    if warehouse_id:
        parts.append(f'wh={warehouse_id}')
    if status:
        parts.append(f'status={status}')
    if search_query:
        parts.append(f'q={search_query}')
    if sort_key:
        parts.append(f'sort={sort_key}')
    if sort_dir:
        parts.append(f'dir={sort_dir}')
    return '&'.join(parts)


def _warehouse_tabs(base_qs, locations, selected_warehouse_id):
    total = base_qs.count()
    tabs = [{
        'id': None,
        'code': '',
        'label': 'Tổng quan kho',
        'count': total,
        'active': selected_warehouse_id is None,
        'counting': base_qs.filter(status=STOCKTAKE_STATUS_COUNTING).count(),
    }]
    status_counts = {
        row['location_id']: row
        for row in base_qs.values('location_id').annotate(
            total=Count('id'),
            counting=Count('id', filter=Q(status=STOCKTAKE_STATUS_COUNTING)),
        )
    }
    for location in locations:
        stats = status_counts.get(location.pk, {})
        tabs.append({
            'id': location.pk,
            'code': location.code,
            'label': location.name or location.code,
            'count': stats.get('total', 0),
            'counting': stats.get('counting', 0),
            'active': selected_warehouse_id == location.pk,
        })
    return tabs


def _warehouse_groups(base_qs, locations):
    groups = []
    for location in locations:
        loc_qs = base_qs.filter(location=location).order_by('-stocktake_date', '-pk')
        total = loc_qs.count()
        if total == 0:
            continue
        preview = list(loc_qs[:STOCKTAKE_WH_PREVIEW])
        groups.append({
            'location': location,
            'stocktakes': preview,
            'total': total,
            'has_more': total > len(preview),
            'counting': loc_qs.filter(status=STOCKTAKE_STATUS_COUNTING).count(),
            'draft': loc_qs.filter(status=STOCKTAKE_STATUS_DRAFT).count(),
            'closed': loc_qs.filter(status=STOCKTAKE_STATUS_CLOSED).count(),
        })
    return groups


@module_perm_required(MODULE_KHO_NPL, 'view')
def stocktake_list(request):
    search_query = get_search_query(request)
    status = doc_status_filter(request, choices=STOCKTAKE_STATUS_FILTER_CHOICES)
    warehouse_id = _parse_warehouse_id(request)
    locations = list(source_locations_qs().order_by('code'))
    valid_wh_ids = {loc.pk for loc in locations}
    if warehouse_id and warehouse_id not in valid_wh_ids:
        warehouse_id = None

    base_qs = _stocktake_filtered_qs(search_query, status)
    warehouse_tabs = _warehouse_tabs(base_qs, locations, warehouse_id)

    list_columns = _stocktake_list_columns(single_warehouse=bool(warehouse_id))
    total_col_weight = sum(c['weight'] for c in list_columns)

    if warehouse_id:
        sort_key, sort_dir, order = doc_list_sort(
            request, STOCKTAKE_LIST_SORT_FIELDS, default_key='stocktake_date',
        )
        qs = base_qs.filter(location_id=warehouse_id).order_by(order, '-pk')
        page_obj, query_string = paginate_queryset(request, qs)
        selected_location = next((loc for loc in locations if loc.pk == warehouse_id), None)
        warehouse_groups = []
        list_mode = 'warehouse'
    else:
        sort_key, sort_dir = 'stocktake_date', 'desc'
        page_obj = None
        query_string = _stocktake_list_query_string(
            warehouse_id=None,
            status=status,
            search_query=search_query,
        )
        selected_location = None
        warehouse_groups = _warehouse_groups(base_qs, locations)
        list_mode = 'overview'

    return render(request, 'kho_npl/stocktake_list.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STOCKTAKE_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status),
        'list_columns': list_columns,
        'total_col_weight': total_col_weight,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'warehouse_tabs': warehouse_tabs,
        'warehouse_groups': warehouse_groups,
        'selected_warehouse_id': warehouse_id,
        'selected_location': selected_location,
        'list_mode': list_mode,
        'status_labels': STOCKTAKE_STATUS_LABELS,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def stocktake_detail(request, pk):
    lines_qs = StocktakeLine.objects.select_related('material__unit', 'location').order_by('material__code')
    stocktake = get_object_or_404(
        Stocktake.objects.select_related('created_by', 'location').prefetch_related(
            Prefetch('lines', queryset=lines_qs),
        ),
        pk=pk,
    )
    variance_lines = [
        line for line in stocktake.lines.all()
        if line.actual_qty is not None and line.actual_qty != line.system_qty
    ]
    return render(request, 'kho_npl/stocktake_detail.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'stocktake': stocktake,
        'variance_lines': variance_lines,
        'line_count': _stocktake_line_count(stocktake),
        'can_count': stocktake_can_count(stocktake),
        'is_editable': stocktake_is_editable(stocktake),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def stocktake_create(request):
    form = StocktakeForm(request.POST or None, request.FILES or None)
    if request.method != 'POST':
        wh_id = _parse_warehouse_id(request)
        if wh_id and source_locations_qs().filter(pk=wh_id).exists():
            form.initial.setdefault('location', wh_id)
    if request.method == 'POST' and form.is_valid():
        stocktake = form.save(commit=False)
        stocktake.number = next_stocktake_number()
        stocktake.created_by = request.user
        stocktake.status = STOCKTAKE_STATUS_DRAFT
        stocktake.save()
        messages.success(
            request,
            f'Đã tạo kỳ kiểm kê {stocktake.number} — kho {stocktake.location.code}.',
        )
        return redirect('kho_npl:stocktake_detail', pk=stocktake.pk)
    return render(request, 'kho_npl/stocktake_form.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'form': form,
        'cancel_url': reverse('kho_npl:stocktake_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def stocktake_start(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk)
    if request.method == 'POST':
        try:
            start_stocktake_counting(stocktake)
            messages.success(
                request,
                f'Đã tải tồn kho {stocktake.location.code} — bắt đầu kiểm kê.',
            )
            return redirect('kho_npl:stocktake_count', pk=pk)
        except StocktakeWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:stocktake_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def stocktake_count(request, pk):
    stocktake = get_object_or_404(
        Stocktake.objects.select_related('location'),
        pk=pk,
    )
    if not stocktake_can_count(stocktake):
        messages.error(request, 'Kỳ kiểm kê không thể nhập số liệu.')
        return redirect('kho_npl:stocktake_detail', pk=pk)
    lines_qs = _stocktake_lines_qs(stocktake)
    if request.method == 'POST':
        formset = StocktakeLineFormSet(
            request.POST,
            instance=stocktake,
            prefix='lines',
            queryset=lines_qs,
        )
        action = request.POST.get('action', 'save')
        if formset.is_valid():
            formset.save()
            if action == 'close':
                try:
                    close_stocktake(stocktake, request.user)
                    messages.success(request, f'Đã chốt kỳ {stocktake.number} và cập nhật tồn chênh lệch.')
                    return redirect('kho_npl:stocktake_detail', pk=pk)
                except StocktakeWorkflowError as exc:
                    messages.error(request, str(exc))
            else:
                messages.success(request, 'Đã lưu tồn thực tế.')
                return redirect('kho_npl:stocktake_count', pk=pk)
    else:
        formset = StocktakeLineFormSet(
            instance=stocktake,
            prefix='lines',
            queryset=lines_qs,
        )
    return render(request, 'kho_npl/stocktake_count.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'stocktake': stocktake,
        'formset': formset,
        'line_count': lines_qs.count(),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def stocktake_reload(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk)
    if request.method == 'POST':
        try:
            count = populate_stocktake_lines(stocktake)
            messages.success(request, f'Đã tải {count} dòng tồn tại kho {stocktake.location.code}.')
        except StocktakeWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:stocktake_detail', pk=pk)
