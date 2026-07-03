from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.material_search import apply_smart_search
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import (
    STOCKTAKE_STATUS_DRAFT,
    STOCKTAKE_STATUS_LABELS,
)
from kho_npl.filter_utils import parse_int_ids
from kho_npl.services.scrap_warehouse import source_locations_qs
from kho_npl.forms import StocktakeForm, StocktakeLineFormSet
from kho_npl.models import Stocktake, StocktakeLine
from kho_npl.services.doc_numbers import next_stocktake_number
from kho_npl.services.stocktake_export import (
    stocktake_detail_export_response,
    stocktake_list_export_response,
)
from kho_npl.services.stocktakes import (
    StocktakeWorkflowError,
    close_stocktake,
    populate_stocktake_lines,
    start_stocktake_counting,
    stocktake_can_count,
    stocktake_is_editable,
)
from kho_npl.doc_list_columns import (
    STOCKTAKE_DETAIL_LINE_COLUMNS,
    STOCKTAKE_DETAIL_LINE_TOTAL_COL_WEIGHT,
    STOCKTAKE_LIST_COLUMNS,
    STOCKTAKE_LIST_SORT_FIELDS,
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


def _parse_warehouse_ids(request, valid_ids: set[int]) -> list[int]:
    return [pk for pk in parse_int_ids(request, 'wh') if pk in valid_ids]


def _stocktake_filtered_qs(search_query, status):
    qs = Stocktake.objects.select_related('created_by', 'location')
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = apply_smart_search(qs, search_query, ('number', 'name', 'location__name'))
    return qs


def _stocktake_list_columns(*, single_warehouse: bool):
    if single_warehouse:
        return [c for c in STOCKTAKE_LIST_COLUMNS if c['key'] != 'location']
    return STOCKTAKE_LIST_COLUMNS


def _stocktake_list_state(request):
    search_query = get_search_query(request)
    status = doc_status_filter(request, choices=STOCKTAKE_STATUS_FILTER_CHOICES)
    locations = list(source_locations_qs().order_by('code'))
    valid_wh_ids = {loc.pk for loc in locations}
    warehouse_ids = _parse_warehouse_ids(request, valid_wh_ids)
    base_qs = _stocktake_filtered_qs(search_query, status)
    if warehouse_ids:
        base_qs = base_qs.filter(location_id__in=warehouse_ids)
    return {
        'search_query': search_query,
        'status': status,
        'locations': locations,
        'warehouse_ids': warehouse_ids,
        'qs': base_qs,
    }


@module_perm_required(MODULE_KHO_NPL, 'view')
def stocktake_list(request):
    state = _stocktake_list_state(request)
    search_query = state['search_query']
    status = state['status']
    locations = state['locations']
    warehouse_ids = state['warehouse_ids']
    base_qs = state['qs']

    single_warehouse = len(warehouse_ids) == 1
    list_columns = _stocktake_list_columns(single_warehouse=single_warehouse)
    total_col_weight = sum(c['weight'] for c in list_columns)

    default_sort = 'stocktake_date' if single_warehouse else 'location'
    sort_key, sort_dir, order = doc_list_sort(
        request, STOCKTAKE_LIST_SORT_FIELDS, default_key=default_sort,
    )
    page_obj, query_string = paginate_queryset(request, base_qs.order_by(order, '-pk'))
    selected_location = (
        next((loc for loc in locations if loc.pk == warehouse_ids[0]), None)
        if single_warehouse else None
    )

    return render(request, 'kho_npl/stocktake_list.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STOCKTAKE_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status or warehouse_ids),
        'list_columns': list_columns,
        'total_col_weight': total_col_weight,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'locations': locations,
        'selected_warehouse_ids': warehouse_ids,
        'selected_location': selected_location,
        'status_labels': STOCKTAKE_STATUS_LABELS,
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def stocktake_list_export(request):
    state = _stocktake_list_state(request)
    sort_key, sort_dir, order = doc_list_sort(
        request, STOCKTAKE_LIST_SORT_FIELDS,
        default_key='stocktake_date' if len(state['warehouse_ids']) == 1 else 'location',
    )
    return stocktake_list_export_response(state['qs'].order_by(order, '-pk'))


@module_perm_required(MODULE_KHO_NPL, 'export')
def stocktake_detail_export(request, pk):
    lines_qs = StocktakeLine.objects.select_related('material__unit').order_by('material__code')
    stocktake = get_object_or_404(
        Stocktake.objects.select_related('created_by', 'location').prefetch_related(
            Prefetch('lines', queryset=lines_qs),
        ),
        pk=pk,
    )
    return stocktake_detail_export_response(stocktake)


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
        'line_columns': STOCKTAKE_DETAIL_LINE_COLUMNS,
        'line_total_col_weight': STOCKTAKE_DETAIL_LINE_TOTAL_COL_WEIGHT,
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def stocktake_create(request):
    form = StocktakeForm(request.POST or None, request.FILES or None)
    if request.method != 'POST':
        valid_wh_ids = set(source_locations_qs().values_list('pk', flat=True))
        wh_ids = _parse_warehouse_ids(request, valid_wh_ids)
        if wh_ids:
            form.initial.setdefault('location', wh_ids[0])
    if request.method == 'POST' and form.is_valid():
        stocktake = form.save(commit=False)
        stocktake.number = next_stocktake_number()
        stocktake.created_by = request.user
        stocktake.status = STOCKTAKE_STATUS_DRAFT
        stocktake.save()
        messages.success(
            request,
            f'Đã tạo kỳ kiểm kê {stocktake.number} — kho {stocktake.location.display_label()}.',
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
                f'Đã tải tồn kho {stocktake.location.display_label()} — bắt đầu kiểm kê.',
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
            messages.success(request, f'Đã tải {count} dòng tồn tại kho {stocktake.location.display_label()}.')
        except StocktakeWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:stocktake_detail', pk=pk)
