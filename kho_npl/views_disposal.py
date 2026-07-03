from django.contrib import messages
from django.db import transaction
from django.db.models import Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.material_search import apply_smart_search
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT
from kho_npl.forms import StockDisposalForm, StockDisposalLineFormSet
from kho_npl.models import StockDisposal
from kho_npl.services.disposals import (
    DisposalWorkflowError,
    cancel_stock_disposal,
    disposal_is_editable,
    post_stock_disposal,
)
from kho_npl.services.doc_numbers import next_disposal_number
from kho_npl.doc_list_columns import (
    DISPOSAL_LIST_COLUMNS,
    DISPOSAL_LIST_SORT_FIELDS,
    DISPOSAL_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.doc_list_utils import DOC_STATUS_FILTER_CHOICES, doc_list_sort, doc_status_filter
from kho_npl.services.scrap_warehouse import get_scrap_location
from kho_npl.view_utils import nav_context, perm_context


def _scrap_warehouse_context() -> dict:
    return {'scrap_warehouse_label': get_scrap_location().display_label()}


def _save_disposal_form(request, disposal, *, is_create: bool):
    form = StockDisposalForm(request.POST, request.FILES, instance=disposal)
    formset = StockDisposalLineFormSet(request.POST, instance=disposal, prefix='lines')
    if not (form.is_valid() and formset.is_valid()):
        return form, formset, None

    with transaction.atomic():
        doc = form.save(commit=False)
        if is_create:
            doc.number = next_disposal_number()
            doc.created_by = request.user
            doc.status = DOC_STATUS_DRAFT
        doc.save()
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def disposal_list(request):
    search_query = get_search_query(request)
    status = doc_status_filter(request, choices=DOC_STATUS_FILTER_CHOICES)
    sort_key, sort_dir, order = doc_list_sort(request, DISPOSAL_LIST_SORT_FIELDS, default_key='disposal_date')
    qs = (
        StockDisposal.objects.select_related('created_by', 'posted_by')
        .annotate(source_location_sort=Min('lines__location__name'))
        .prefetch_related('lines__location')
    )
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = apply_smart_search(
            qs,
            search_query,
            ('number', 'lines__location__name', 'notes'),
        ).distinct()
    qs = qs.order_by(order, '-pk')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/disposal_list.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': DOC_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status),
        'list_columns': DISPOSAL_LIST_COLUMNS,
        'total_col_weight': DISPOSAL_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        **_scrap_warehouse_context(),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def disposal_detail(request, pk):
    disposal = get_object_or_404(
        StockDisposal.objects.select_related('created_by', 'posted_by')
        .prefetch_related('lines__material__unit', 'lines__location'),
        pk=pk,
    )
    return render(request, 'kho_npl/disposal_detail.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'disposal': disposal,
        'is_editable': disposal_is_editable(disposal),
        **_scrap_warehouse_context(),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def disposal_create(request):
    disposal = StockDisposal()
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_disposal_form(request, disposal, is_create=True)
        if doc:
            if action == 'post':
                try:
                    post_stock_disposal(doc, request.user)
                    messages.success(
                        request,
                        f'Đã ghi sổ phiếu {doc.number} — hàng chuyển sang {get_scrap_location().display_label()}.',
                    )
                except DisposalWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:disposal_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:disposal_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockDisposalForm(instance=disposal)
        formset = StockDisposalLineFormSet(instance=disposal, prefix='lines')
    return render(request, 'kho_npl/disposal_form.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'disposal': disposal,
        **_scrap_warehouse_context(),
        'cancel_url': reverse('kho_npl:disposal_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def disposal_edit(request, pk):
    disposal = get_object_or_404(StockDisposal, pk=pk)
    if not disposal_is_editable(disposal):
        messages.error(request, 'Phiếu đã ghi sổ hoặc đã hủy — không thể sửa.')
        return redirect('kho_npl:disposal_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_disposal_form(request, disposal, is_create=False)
        if doc:
            if action == 'post':
                try:
                    post_stock_disposal(doc, request.user)
                    messages.success(request, f'Đã ghi sổ phiếu {doc.number}.')
                except DisposalWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:disposal_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:disposal_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockDisposalForm(instance=disposal)
        formset = StockDisposalLineFormSet(instance=disposal, prefix='lines')
    return render(request, 'kho_npl/disposal_form.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'disposal': disposal,
        **_scrap_warehouse_context(),
        'cancel_url': reverse('kho_npl:disposal_detail', args=[disposal.pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def disposal_post(request, pk):
    disposal = get_object_or_404(StockDisposal, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_disposal(disposal, request.user)
            messages.success(request, f'Đã ghi sổ phiếu {disposal.number}.')
        except DisposalWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:disposal_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def disposal_cancel(request, pk):
    disposal = get_object_or_404(StockDisposal, pk=pk)
    if request.method == 'POST':
        try:
            cancel_stock_disposal(disposal)
            messages.success(request, f'Đã hủy phiếu {disposal.number}.')
            return redirect('kho_npl:disposal_list')
        except DisposalWorkflowError as exc:
            messages.error(request, str(exc))
            return redirect('kho_npl:disposal_detail', pk=pk)
    return render(request, 'kho_npl/disposal_confirm_cancel.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'disposal': disposal,
    })
