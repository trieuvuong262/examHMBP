from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.menu_permissions import user_can_create_menu
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.forms import (
    StockReceiptForm,
    StockReceiptLineFormSet,
    StockReceiptLineNotesFormSet,
    StockReceiptNotesForm,
)
from kho_npl.models import StockReceipt
from kho_npl.services.doc_numbers import next_receipt_number
from kho_npl.services.receipts import (
    ReceiptWorkflowError,
    cancel_stock_receipt,
    post_stock_receipt,
    receipt_is_editable,
)
from kho_npl.doc_list_columns import (
    RECEIPT_LIST_COLUMNS,
    RECEIPT_LIST_SORT_FIELDS,
    RECEIPT_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.doc_list_utils import RECEIPT_STATUS_FILTER_CHOICES, doc_list_sort, doc_status_filter
from kho_npl.view_utils import nav_context, perm_context


def _receipt_form_context(request, *, form, formset, is_edit, cancel_url, receipt=None):
    return {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'form': form,
        'formset': formset,
        'is_edit': is_edit,
        'cancel_url': cancel_url,
        'can_create_supplier': user_can_create_menu(request.user, MODULE_KHO_NPL, 'settings'),
        **({'receipt': receipt} if receipt else {}),
    }


def _save_receipt_form(request, receipt, *, is_create: bool):
    form = StockReceiptForm(
        request.POST, request.FILES, instance=receipt, operator=request.user,
    )
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
    status = doc_status_filter(request, choices=RECEIPT_STATUS_FILTER_CHOICES)
    sort_key, sort_dir, order = doc_list_sort(request, RECEIPT_LIST_SORT_FIELDS, default_key='receipt_date')
    qs = StockReceipt.objects.select_related('supplier', 'received_by', 'created_by')
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(po_number__icontains=search_query)
            | Q(supplier__name__icontains=search_query)
        )
    qs = qs.order_by(order, '-pk')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_npl/receipt_list.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': RECEIPT_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status),
        'list_columns': RECEIPT_LIST_COLUMNS,
        'total_col_weight': RECEIPT_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
    })


def receipt_notes_editable(receipt: StockReceipt) -> bool:
    return receipt.status == DOC_STATUS_POSTED


@module_perm_required(MODULE_KHO_NPL, 'view')
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        StockReceipt.objects.select_related(
            'supplier', 'received_by', 'checked_by', 'created_by',
        ).prefetch_related('lines__material', 'lines__material__unit', 'lines__location'),
        pk=pk,
    )
    perms = perm_context(request.user, 'receipts')
    can_edit_notes = receipt_notes_editable(receipt) and perms.get('can_update')
    notes_form = StockReceiptNotesForm(instance=receipt) if can_edit_notes else None
    line_notes_formset = StockReceiptLineNotesFormSet(instance=receipt) if can_edit_notes else None
    return render(request, 'kho_npl/receipt_detail.html', {
        **nav_context('receipts', user=request.user),
        **perms,
        'receipt': receipt,
        'is_editable': receipt_is_editable(receipt),
        'can_edit_notes': can_edit_notes,
        'notes_form': notes_form,
        'line_notes_formset': line_notes_formset,
    })


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def receipt_update_notes(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:receipt_detail', pk=pk)
    if not receipt_notes_editable(receipt):
        messages.error(request, 'Chỉ phiếu đã nhập kho mới được sửa ghi chú tại đây.')
        return redirect('kho_npl:receipt_detail', pk=pk)
    form = StockReceiptNotesForm(request.POST, instance=receipt)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.save(update_fields=['notes'])
        messages.success(request, f'Đã cập nhật ghi chú phiếu {receipt.number}.')
    else:
        messages.error(request, 'Không lưu được ghi chú — kiểm tra lại nội dung.')
    return redirect('kho_npl:receipt_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def receipt_update_line_notes(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if request.method != 'POST':
        return redirect('kho_npl:receipt_detail', pk=pk)
    if not receipt_notes_editable(receipt):
        messages.error(request, 'Chỉ phiếu đã nhập kho mới được sửa ghi chú dòng tại đây.')
        return redirect('kho_npl:receipt_detail', pk=pk)
    formset = StockReceiptLineNotesFormSet(request.POST, instance=receipt)
    if formset.is_valid():
        formset.save()
        messages.success(request, f'Đã cập nhật ghi chú dòng phiếu {receipt.number}.')
    else:
        messages.error(request, 'Không lưu được ghi chú dòng — kiểm tra lại nội dung.')
    return redirect('kho_npl:receipt_detail', pk=pk)


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
                    messages.success(request, f'Phiếu {doc.number} đã nhập kho và cập nhật tồn.')
                except ReceiptWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:receipt_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:receipt_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockReceiptForm(instance=receipt, operator=request.user)
        formset = StockReceiptLineFormSet(instance=receipt, prefix='lines')
    return render(request, 'kho_npl/receipt_form.html', _receipt_form_context(
        request,
        form=form,
        formset=formset,
        is_edit=False,
        cancel_url=reverse('kho_npl:receipt_list'),
    ))


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def receipt_edit(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if not receipt_is_editable(receipt):
        messages.error(request, 'Phiếu đã nhập kho hoặc đã hủy — không thể sửa.')
        return redirect('kho_npl:receipt_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_receipt_form(request, receipt, is_create=False)
        if doc:
            if action == 'post':
                try:
                    post_stock_receipt(doc, request.user)
                    messages.success(request, f'Phiếu {doc.number} đã nhập kho và cập nhật tồn.')
                except ReceiptWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:receipt_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:receipt_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockReceiptForm(instance=receipt, operator=request.user)
        formset = StockReceiptLineFormSet(instance=receipt, prefix='lines')
    return render(request, 'kho_npl/receipt_form.html', _receipt_form_context(
        request,
        form=form,
        formset=formset,
        is_edit=True,
        cancel_url=reverse('kho_npl:receipt_detail', args=[receipt.pk]),
        receipt=receipt,
    ))


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def receipt_post(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk)
    if request.method == 'POST':
        try:
            post_stock_receipt(receipt, request.user)
            messages.success(request, f'Phiếu {receipt.number} đã nhập kho.')
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
