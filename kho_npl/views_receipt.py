from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT
from kho_npl.forms import StockReceiptForm, StockReceiptLineFormSet
from kho_npl.models import StockReceipt
from kho_npl.services.doc_numbers import next_receipt_number
from kho_npl.services.receipts import (
    ReceiptWorkflowError,
    cancel_stock_receipt,
    post_stock_receipt,
    receipt_is_editable,
)
from kho_npl.view_utils import nav_context, perm_context


def _save_receipt_form(request, receipt, *, is_create: bool):
    form = StockReceiptForm(request.POST, instance=receipt)
    formset = StockReceiptLineFormSet(request.POST, instance=receipt, prefix='lines')
    if not (form.is_valid() and formset.is_valid()):
        return form, formset, None

    with transaction.atomic():
        doc = form.save(commit=False)
        if is_create:
            doc.number = next_receipt_number()
            doc.created_by = request.user
            doc.status = DOC_STATUS_DRAFT
        doc.save()
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def receipt_list(request):
    search_query = get_search_query(request)
    qs = StockReceipt.objects.select_related('supplier', 'received_by', 'created_by')
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(po_number__icontains=search_query)
            | Q(supplier__name__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/receipt_list.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        StockReceipt.objects.select_related(
            'supplier', 'received_by', 'checked_by', 'created_by',
        ).prefetch_related('lines__material', 'lines__location'),
        pk=pk,
    )
    return render(request, 'kho_npl/receipt_detail.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'receipt': receipt,
        'is_editable': receipt_is_editable(receipt),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def receipt_create(request):
    receipt = StockReceipt()
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_receipt_form(request, receipt, is_create=True)
        if doc:
            if action == 'post':
                try:
                    post_stock_receipt(doc, request.user)
                    messages.success(request, f'Đã ghi sổ phiếu {doc.number} và cập nhật tồn kho.')
                except ReceiptWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:receipt_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:receipt_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockReceiptForm(instance=receipt)
        formset = StockReceiptLineFormSet(instance=receipt, prefix='lines')
    return render(request, 'kho_npl/receipt_form.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:receipt_list'),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def receipt_edit(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if not receipt_is_editable(receipt):
        messages.error(request, 'Phiếu đã ghi sổ hoặc đã hủy — không thể sửa.')
        return redirect('kho_npl:receipt_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_receipt_form(request, receipt, is_create=False)
        if doc:
            if action == 'post':
                try:
                    post_stock_receipt(doc, request.user)
                    messages.success(request, f'Đã ghi sổ phiếu {doc.number} và cập nhật tồn kho.')
                except ReceiptWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:receipt_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:receipt_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockReceiptForm(instance=receipt)
        formset = StockReceiptLineFormSet(instance=receipt, prefix='lines')
    return render(request, 'kho_npl/receipt_form.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'receipt': receipt,
        'cancel_url': reverse('kho_npl:receipt_detail', args=[receipt.pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def receipt_post(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_receipt(receipt, request.user)
            messages.success(request, f'Đã ghi sổ phiếu {receipt.number}.')
        except ReceiptWorkflowError as exc:
            messages.error(request, str(exc))
    return redirect('kho_npl:receipt_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def receipt_cancel(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if request.method == 'POST':
        try:
            cancel_stock_receipt(receipt)
            messages.success(request, f'Đã hủy phiếu {receipt.number}.')
            return redirect('kho_npl:receipt_list')
        except ReceiptWorkflowError as exc:
            messages.error(request, str(exc))
            return redirect('kho_npl:receipt_detail', pk=pk)
    return render(request, 'kho_npl/receipt_confirm_cancel.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'receipt': receipt,
    })
