from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import ADJUST_STATUS_PENDING
from kho_npl.forms import StockAdjustmentForm
from kho_npl.models import StockAdjustment
from kho_npl.services.adjustments import (
    AdjustmentWorkflowError,
    adjustment_is_editable,
    approve_stock_adjustment,
    reject_stock_adjustment,
)
from kho_npl.services.doc_numbers import next_adjustment_number
from kho_npl.view_utils import nav_context, perm_context


@module_perm_required(MODULE_KHO_NPL, 'view')
def adjustment_list(request):
    search_query = get_search_query(request)
    qs = StockAdjustment.objects.select_related('material', 'location', 'proposed_by', 'approved_by')
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(material__code__icontains=search_query)
            | Q(material__name__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/adjustment_list.html', {
        **nav_context('adjustments'),
        **perm_context(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def adjustment_detail(request, pk):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related(
            'material', 'location', 'proposed_by', 'approved_by',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/adjustment_detail.html', {
        **nav_context('adjustments'),
        **perm_context(request.user),
        'adjustment': adjustment,
        'is_editable': adjustment_is_editable(adjustment),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def adjustment_create(request):
    form = StockAdjustmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        adjustment = form.save(commit=False)
        adjustment.number = next_adjustment_number()
        adjustment.proposed_by = request.user
        adjustment.status = ADJUST_STATUS_PENDING
        adjustment.save()
        messages.success(request, f'Đã tạo phiếu điều chỉnh {adjustment.number} — chờ duyệt.')
        return redirect('kho_npl:adjustment_detail', pk=adjustment.pk)
    return render(request, 'kho_npl/adjustment_form.html', {
        **nav_context('adjustments'),
        **perm_context(request.user),
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:adjustment_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def adjustment_approve(request, pk):
    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            approve_stock_adjustment(adjustment, request.user)
            messages.success(request, f'Đã duyệt phiếu {adjustment.number} và cập nhật tồn.')
        except AdjustmentWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:adjustment_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def adjustment_reject(request, pk):
    adjustment = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            reject_stock_adjustment(adjustment, request.user)
            messages.success(request, f'Đã từ chối phiếu {adjustment.number}.')
        except AdjustmentWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:adjustment_detail', pk=pk)
