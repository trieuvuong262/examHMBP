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
    TRANSFER_LIST_FILTER_ALL,
    TRANSFER_LIST_STATUS_FILTERS,
    TRANSFER_STATUS_CANCELLED,
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
    TRANSFER_TAB_CHOICES,
    TRANSFER_TAB_CHUYEN,
    TRANSFER_TAB_DANH_SACH,
    TRANSFER_TAB_NHAN,
    TRANSFER_TAB_NHAP,
)
from kho_npl.forms import (
    StockTransferForm,
    StockTransferLineFormSet,
    transfer_post_has_active_lines,
)
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
from kho_npl.doc_list_columns import (
    TRANSFER_LIST_COLUMNS,
    TRANSFER_LIST_COLUMNS_WITH_STATUS,
    TRANSFER_LIST_SORT_FIELDS,
    TRANSFER_LIST_TOTAL_COL_WEIGHT,
    TRANSFER_LIST_TOTAL_COL_WEIGHT_WITH_STATUS,
)
from kho_npl.doc_list_utils import doc_list_sort
from kho_npl.view_utils import nav_context, perm_context

VALID_TABS = {TRANSFER_TAB_NHAP, TRANSFER_TAB_CHUYEN, TRANSFER_TAB_NHAN, TRANSFER_TAB_DANH_SACH}

VALID_LIST_STATUS_FILTERS = {choice[0] for choice in TRANSFER_LIST_STATUS_FILTERS}

# Nhập = tạo phiếu | Chuyển = nháp chờ gửi | Nhận = đang chuyển chờ xác nhận
TAB_STATUS_MAP = {
    TRANSFER_TAB_CHUYEN: [TRANSFER_STATUS_DRAFT],
    TRANSFER_TAB_NHAN: [TRANSFER_STATUS_IN_TRANSIT],
}


def _resolve_tab(request) -> str:
    tab = (request.GET.get('tab') or TRANSFER_TAB_DANH_SACH).strip().lower()
    return tab if tab in VALID_TABS else TRANSFER_TAB_DANH_SACH


def _resolve_list_status(request) -> str:
    status = (request.GET.get('status') or TRANSFER_LIST_FILTER_ALL).strip().lower()
    return status if status in VALID_LIST_STATUS_FILTERS else TRANSFER_LIST_FILTER_ALL


def _transfer_list_url(tab: str, *, status: str = TRANSFER_LIST_FILTER_ALL) -> str:
    url = reverse('kho_npl:transfer_hub') + f'?tab={tab}'
    if tab == TRANSFER_TAB_DANH_SACH and status:
        url += f'&status={status}'
    return url


def _tab_for_transfer(transfer: StockTransfer) -> str:
    if transfer.status == TRANSFER_STATUS_RECEIVED:
        return TRANSFER_TAB_DANH_SACH
    if transfer.status == TRANSFER_STATUS_IN_TRANSIT:
        return TRANSFER_TAB_NHAN
    return TRANSFER_TAB_CHUYEN


def _warehouse_locked(transfer) -> bool:
    return bool(transfer.pk and transfer.lines.exists())


def _save_transfer_form(request, transfer, *, is_create: bool):
    wh_locked = _warehouse_locked(transfer)
    form = StockTransferForm(
        request.POST,
        request.FILES,
        instance=transfer,
        warehouse_locked=wh_locked,
    )
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


def _hub_list_context(request, tab: str):
    search_query = get_search_query(request)
    qs = StockTransfer.objects.select_related(
        'from_location', 'to_location', 'created_by', 'sent_by', 'received_by',
    )
    if tab == TRANSFER_TAB_DANH_SACH:
        list_status = _resolve_list_status(request)
        if list_status:
            qs = qs.filter(status=list_status)
        else:
            qs = qs.exclude(status=TRANSFER_STATUS_CANCELLED)
    else:
        qs = qs.filter(status__in=TAB_STATUS_MAP[tab])
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(from_location__code__icontains=search_query)
            | Q(to_location__code__icontains=search_query)
            | Q(notes__icontains=search_query)
        )
    sort_key, sort_dir, order = doc_list_sort(request, TRANSFER_LIST_SORT_FIELDS, default_key='transfer_date')
    qs = qs.order_by(order, '-pk')
    page_obj, query_string = paginate_queryset(request, qs)
    list_status = _resolve_list_status(request) if tab == TRANSFER_TAB_DANH_SACH else ''
    list_columns = (
        TRANSFER_LIST_COLUMNS_WITH_STATUS if tab == TRANSFER_TAB_DANH_SACH
        else TRANSFER_LIST_COLUMNS
    )
    total_col_weight = (
        TRANSFER_LIST_TOTAL_COL_WEIGHT_WITH_STATUS if tab == TRANSFER_TAB_DANH_SACH
        else TRANSFER_LIST_TOTAL_COL_WEIGHT
    )
    ctx = {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'list_columns': list_columns,
        'total_col_weight': total_col_weight,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'has_filters': bool(search_query or list_status),
    }
    if tab == TRANSFER_TAB_DANH_SACH:
        ctx['list_status'] = list_status
        ctx['list_status_filters'] = TRANSFER_LIST_STATUS_FILTERS
        ctx['status_choices'] = TRANSFER_LIST_STATUS_FILTERS
        ctx['selected_status'] = list_status
    return ctx


@module_perm_required(MODULE_KHO_NPL, 'view')
def transfer_hub(request):
    tab = _resolve_tab(request)
    ctx = {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'tab': tab,
        'tab_choices': TRANSFER_TAB_CHOICES,
        'list_url': _transfer_list_url(tab),
        'list_status_filters': TRANSFER_LIST_STATUS_FILTERS,
        'list_status': _resolve_list_status(request) if tab == TRANSFER_TAB_DANH_SACH else '',
        'search_query': get_search_query(request) if tab != TRANSFER_TAB_NHAP else '',
        'show_transfer_search': tab != TRANSFER_TAB_NHAP,
    }

    if tab == TRANSFER_TAB_NHAP:
        if not ctx.get('can_create'):
            messages.info(request, 'Bạn không có quyền tạo phiếu chuyển kho.')
            return redirect(_transfer_list_url(TRANSFER_TAB_CHUYEN))
        form = StockTransferForm()
        formset = StockTransferLineFormSet(prefix='lines')
        ctx.update({
            'form': form,
            'formset': formset,
            'form_action_url': reverse('kho_npl:transfer_create'),
            'warehouse_locked': False,
        })
        return render(request, 'kho_npl/transfer_hub.html', ctx)

    ctx.update(_hub_list_context(request, tab))
    return render(request, 'kho_npl/transfer_hub.html', ctx)


@module_perm_required(MODULE_KHO_NPL, 'view')
def transfer_detail(request, pk):
    transfer = get_object_or_404(
        StockTransfer.objects.select_related(
            'from_location', 'to_location', 'created_by', 'sent_by', 'received_by',
        ).prefetch_related('lines__material__unit'),
        pk=pk,
    )
    tab = _tab_for_transfer(transfer)
    list_status = transfer.status if tab == TRANSFER_TAB_DANH_SACH else TRANSFER_LIST_FILTER_ALL
    return render(request, 'kho_npl/transfer_detail.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'transfer': transfer,
        'tab': tab,
        'tab_choices': TRANSFER_TAB_CHOICES,
        'list_status_filters': TRANSFER_LIST_STATUS_FILTERS,
        'list_status': transfer.status if tab == TRANSFER_TAB_DANH_SACH else '',
        'search_query': '',
        'is_editable': transfer_is_editable(transfer),
        'can_send': transfer_can_send(transfer),
        'can_receive': transfer_can_receive(transfer),
        'list_url': _transfer_list_url(tab, status=list_status),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def transfer_create(request):
    if request.method != 'POST':
        return redirect(_transfer_list_url(TRANSFER_TAB_NHAP))

    transfer = StockTransfer()
    form, formset, doc = _save_transfer_form(request, transfer, is_create=True)
    if doc:
        messages.success(
            request,
            f'Đã lưu phiếu {doc.number}. Vào tab Chuyển để gửi hàng đi.',
        )
        return redirect(_transfer_list_url(TRANSFER_TAB_CHUYEN))

    return render(request, 'kho_npl/transfer_form.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'form': form,
        'formset': formset,
        'is_edit': False,
        'transfer': transfer,
        'cancel_url': _transfer_list_url(TRANSFER_TAB_NHAP),
        'form_action_url': reverse('kho_npl:transfer_create'),
        'warehouse_locked': _warehouse_locked(transfer),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def transfer_edit(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    if not transfer_is_editable(transfer):
        messages.error(request, 'Phiếu không còn ở trạng thái nháp — không thể sửa.')
        return redirect('kho_npl:transfer_detail', pk=pk)
    if request.method == 'POST':
        form, formset, doc = _save_transfer_form(request, transfer, is_create=False)
        if doc:
            messages.success(request, f'Đã cập nhật phiếu {doc.number}.')
            return redirect('kho_npl:transfer_detail', pk=doc.pk)
    if request.method != 'POST':
        wh_locked = transfer.lines.exists()
        form = StockTransferForm(instance=transfer, warehouse_locked=wh_locked)
        formset = StockTransferLineFormSet(instance=transfer, prefix='lines')
    return render(request, 'kho_npl/transfer_form.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'form': form,
        'formset': formset,
        'is_edit': True,
        'transfer': transfer,
        'cancel_url': reverse('kho_npl:transfer_detail', args=[pk]),
        'form_action_url': reverse('kho_npl:transfer_edit', args=[pk]),
        'warehouse_locked': transfer.lines.exists(),
    })


@module_perm_required_methods(MODULE_KHO_NPL, post='update')
def transfer_send(request, pk):
    transfer = get_object_or_404(StockTransfer, pk=pk)
    try:
        send_stock_transfer(transfer, request.user)
        messages.success(
            request,
            f'Đã chuyển phiếu {transfer.number} — hàng đang trên đường tới {transfer.to_location.code}.',
        )
    except TransferWorkflowError as exc:
        messages.error(request, str(exc))
        return redirect('kho_npl:transfer_detail', pk=pk)
    return redirect(_transfer_list_url(TRANSFER_TAB_NHAN))


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
            messages.success(request, f'Đã xóa phiếu {transfer.number}.')
        except TransferWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect(_transfer_list_url(TRANSFER_TAB_CHUYEN))
    return render(request, 'kho_npl/transfer_confirm_cancel.html', {
        **nav_context('transfers', user=request.user),
        **perm_context(request.user, 'transfers'),
        'transfer': transfer,
        'list_url': _transfer_list_url(TRANSFER_TAB_CHUYEN),
    })
