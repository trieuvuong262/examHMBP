from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import STOCKTAKE_STATUS_DRAFT
from kho_npl.forms import StocktakeForm, StocktakeLineFormSet
from kho_npl.models import Stocktake
from kho_npl.services.doc_numbers import next_stocktake_number
from kho_npl.services.stocktakes import (
    StocktakeWorkflowError,
    close_stocktake,
    populate_stocktake_lines,
    start_stocktake_counting,
    stocktake_can_count,
    stocktake_is_editable,
)
from kho_npl.view_utils import nav_context, perm_context


@module_perm_required(MODULE_KHO_NPL, 'view')
def stocktake_list(request):
    search_query = get_search_query(request)
    qs = Stocktake.objects.select_related('created_by')
    if search_query:
        qs = qs.filter(Q(number__icontains=search_query) | Q(name__icontains=search_query))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/stocktake_list.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def stocktake_detail(request, pk):
    stocktake = get_object_or_404(
        Stocktake.objects.select_related('created_by').prefetch_related(
            'lines__material', 'lines__location',
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
        'can_count': stocktake_can_count(stocktake),
        'is_editable': stocktake_is_editable(stocktake),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def stocktake_create(request):
    form = StocktakeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        stocktake = form.save(commit=False)
        stocktake.number = next_stocktake_number()
        stocktake.created_by = request.user
        stocktake.status = STOCKTAKE_STATUS_DRAFT
        stocktake.save()
        messages.success(request, f'Đã tạo kỳ kiểm kê {stocktake.number}.')
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
            messages.success(request, 'Đã tải tồn hệ thống — bắt đầu kiểm kê.')
            return redirect('kho_npl:stocktake_count', pk=pk)
        except StocktakeWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:stocktake_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def stocktake_count(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk)
    if not stocktake_can_count(stocktake):
        messages.error(request, 'Kỳ kiểm kê không thể nhập số liệu.')
        return redirect('kho_npl:stocktake_detail', pk=pk)
    if request.method == 'POST':
        formset = StocktakeLineFormSet(request.POST, instance=stocktake, prefix='lines')
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
        formset = StocktakeLineFormSet(instance=stocktake, prefix='lines')
    return render(request, 'kho_npl/stocktake_count.html', {
        **nav_context('stocktakes', user=request.user),
        **perm_context(request.user, 'stocktakes'),
        'stocktake': stocktake,
        'formset': formset,
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def stocktake_reload(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk)
    if request.method == 'POST':
        try:
            count = populate_stocktake_lines(stocktake)
            messages.success(request, f'Đã tải {count} dòng tồn hệ thống.')
        except StocktakeWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:stocktake_detail', pk=pk)
