from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import (
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
    TRANSFER_TAB_CHOICES,
    TRANSFER_TAB_CHUYEN,
    TRANSFER_TAB_NHAN,
    TRANSFER_TAB_NHAP,
)
from kho_npl.forms import StockTransferForm, StockTransferLineFormSet
from kho_npl.models import StockTransfer
from kho_npl.services.doc_numbers import next_transfer_number
from kho_npl.services.transfers import (
    TransferWorkflowError,
    cancel_stock_transfer,
    receive_stock_transfer,
    send_stock_transfer,
    transfer_can_receive,
    transfer_can_send,
    transfer_is_editable,
)
from kho_npl.view_utils import nav_context, perm_context

VALID_TABS = {TRANSFER_TAB_NHAP, TRANSFER_TAB_CHUYEN, TRANSFER_TAB_NHAN}

TAB_STATUS_MAP = {
    TRANSFER_TAB_NHAP: [TRANSFER_STATUS_RECEIVED],
    TRANSFER_TAB_CHUYEN: [TRANSFER_STATUS_DRAFT],
    TRANSFER_TAB_NHAN: [TRANSFER_STATUS_IN_TRANSIT],
}


def _resolve_tab(request) -> str:
    tab = (request.GET.get('tab') or TRANSFER_TAB_CHUYEN).strip().lower()
    return tab if tab in VALID_TABS else TRANSFER_TAB_CHUYEN


def _transfer_list_url(tab: str) -> str:
    return reverse('kho_npl:transfer_hub') + f'?tab={tab}'


def _save_transfer_form(request, transfer, *, is_create: bool):
    form = StockTransferForm(request.POST, instance=transfer)
    formset = StockTransferLineFormSet(request.POST, instance=transfer, prefix='lines')
    if not (form.is_valid() and formset.is_valid()):
        return form, formset, None

    with transaction.atomic():
        doc = form.save(commit=False)
        if is_create:
            doc.number = next_transfer_number()
            doc.created_by = request.user
            doc.status = TRANSFER_STATUS_DRAFT
        doc.save()
        formset.instance = doc
        formset.save()
    return form, formset, doc


@module_perm_required(MODULE_KHO_NPL, 'view')
def transfer_hub(request):
    tab = _resolve_tab(request)
    search_query = get_search_query(request)
    qs = StockTransfer.objects.select_related(
        'from_location', 'to_location', 'created_by', 'sent_by', 'received_by',
    ).filter(status__in=TAB_STATUS_MAP[tab])
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(from_location__code__icontains=search_query)
            | Q(to_location__code__icontains=search_query)
            | Q(notes__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    tab_counts = {
        key: StockTransfer.objects.filter(status__in=statuses).count()
        for key, statuses in TAB_STATUS_MAP.items()
    }
    return render(request, 'kho_npl/transfer_hub.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'tab': tab,
        'tab_choices': TRANSFER_TAB_CHOICES,
        'tab_counts': tab_counts,
        'list_url': _transfer_list_url(tab),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def transfer_detail(request, pk):
    transfer = get_object_or_404(
        StockTransfer.objects.select_related(
            'from_location', 'to_location', 'created_by', 'sent_by', 'received_by',
        ).prefetch_related('lines__material__unit'),
        pk=pk,
    )
    if transfer.status == TRANSFER_STATUS_RECEIVED:
        tab = TRANSFER_TAB_NHAP
    elif transfer.status == TRANSFER_STATUS_IN_TRANSIT:
        tab = TRANSFER_TAB_NHAN
    else:
        tab = TRANSFER_TAB_CHUYEN
    tab_counts = {
        key: StockTransfer.objects.filter(status__in=statuses).count()
        for key, statuses in TAB_STATUS_MAP.items()
    }
    return render(request, 'kho_npl/transfer_detail.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'transfer': transfer,
        'tab': tab,
        'tab_choices': TRANSFER_TAB_CHOICES,
        'tab_counts': tab_counts,
        'is_editable': transfer_is_editable(transfer),
        'can_send': transfer_can_send(transfer),
        'can_receive': transfer_can_receive(transfer),
        'list_url': _transfer_list_url(tab),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def transfer_create(request):
    transfer = StockTransfer()
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_transfer_form(request, transfer, is_create=True)
        if doc:
            if action == 'send':
                try:
                    send_stock_transfer(doc, request.user)
                    messages.success(request, f'Đã gửi chuyển phiếu {doc.number} — hàng đang trên đường.')
                except TransferWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:transfer_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã lưu nháp phiếu {doc.number}.')
            return redirect('kho_npl:transfer_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockTransferForm(instance=transfer)
        formset = StockTransferLineFormSet(instance=transfer, prefix='lines')
    return render(request, 'kho_npl/transfer_form.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'transfer': transfer,
        'cancel_url': _transfer_list_url(TRANSFER_TAB_CHUYEN),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def transfer_edit(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    if not transfer_is_editable(transfer):
        messages.error(request, 'Phiếu không còn ở trạng thái nháp — không thể sửa.')
        return redirect('kho_npl:transfer_detail', pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        form, formset, doc = _save_transfer_form(request, transfer, is_create=False)
        if doc:
            if action == 'send':
                try:
                    send_stock_transfer(doc, request.user)
                    messages.success(request, f'Đã gửi chuyển phiếu {doc.number}.')
                except TransferWorkflowError as exc:
                    messages.error(request, str(exc))
                    return redirect('kho_npl:transfer_edit', pk=doc.pk)
            else:
                messages.success(request, f'Đã cập nhật phiếu {doc.number}.')
            return redirect('kho_npl:transfer_detail', pk=doc.pk)
    if request.method != 'POST':
        form = StockTransferForm(instance=transfer)
        formset = StockTransferLineFormSet(instance=transfer, prefix='lines')
    return render(request, 'kho_npl/transfer_form.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'transfer': transfer,
        'cancel_url': reverse('kho_npl:transfer_detail', args=[pk]),
    })


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def transfer_send(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    try:
        send_stock_transfer(transfer, request.user)
        messages.success(request, f'Đã gửi chuyển phiếu {transfer.number}.')
    except TransferWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('kho_npl:transfer_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def transfer_receive(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    try:
        receive_stock_transfer(transfer, request.user)
        messages.success(request, f'Đã nhập kho phiếu {transfer.number} tại {transfer.to_location.code}.')
    except TransferWorkflowError as exc:
        messages.error(request, str(exc))
    return redirect('kho_npl:transfer_detail', pk=pk)


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def transfer_cancel(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        try:
            cancel_stock_transfer(transfer)
            messages.success(request, f'Đã hủy phiếu {transfer.number}.')
        except TransferWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect(_transfer_list_url(TRANSFER_TAB_CHUYEN))
    return render(request, 'kho_npl/transfer_confirm_cancel.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'transfer': transfer,
        'list_url': _transfer_list_url(TRANSFER_TAB_CHUYEN),
    })
