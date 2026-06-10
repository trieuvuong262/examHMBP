from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT, WAREHOUSE_SCRAP_CODE
from kho_npl.forms import StockDisposalForm, StockDisposalLineFormSet
from kho_npl.models import StockDisposal
from kho_npl.services.disposals import (
    DisposalWorkflowError,
    cancel_stock_disposal,
    disposal_is_editable,
    post_stock_disposal,
)
from kho_npl.services.doc_numbers import next_disposal_number
from kho_npl.view_utils import nav_context, perm_context


def _save_disposal_form(request, disposal, *, is_create: bool):
    form = StockDisposalForm(request.POST, instance=disposal)
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
    qs = StockDisposal.objects.select_related('from_location', 'created_by', 'posted_by')
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(from_location__code__icontains=search_query)
            | Q(notes__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/disposal_list.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'scrap_warehouse_code': WAREHOUSE_SCRAP_CODE,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def disposal_detail(request, pk):
    disposal = get_object_or_404(
        StockDisposal.objects.select_related('from_location', 'created_by', 'posted_by')
        .prefetch_related('lines__material__unit'),
        pk=pk,
    )
    return render(request, 'kho_npl/disposal_detail.html', {
        **nav_context('disposals', user=request.user),
        **perm_context(request.user, 'disposals'),
        'disposal': disposal,
        'is_editable': disposal_is_editable(disposal),
        'scrap_warehouse_code': WAREHOUSE_SCRAP_CODE,
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
                        f'Đã ghi sổ phiếu {doc.number} — hàng chuyển sang kho {WAREHOUSE_SCRAP_CODE}.',
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
        'scrap_warehouse_code': WAREHOUSE_SCRAP_CODE,
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
        'scrap_warehouse_code': WAREHOUSE_SCRAP_CODE,
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
