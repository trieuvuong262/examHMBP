"""Phiếu nhập kho thành phẩm — danh sách / chi tiết (tạo từ YCNTP)."""

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.models import StockReceipt
from kho_san_pham.view_utils import nav_context, perm_context

RECEIPT_STATUS_FILTER_CHOICES = (
    ('', 'Tất cả'),
    ('draft', 'Nháp'),
    ('posted', 'Đã nhập kho'),
    ('cancelled', 'Hủy'),
)

_SORT_FIELDS = {
    'number': 'number',
    'receipt_date': 'receipt_date',
    'warehouse': 'warehouse__name',
    'status': 'status',
    'product_code': 'product_code',
    'mo': 'production_order_code',
}


def _status_filter(request) -> str:
    valid = {value for value, _ in RECEIPT_STATUS_FILTER_CHOICES}
    status = (request.GET.get('status') or '').strip().lower()
    if status not in valid:
        return ''
    return status


def _list_sort(request):
    sort_key = (request.GET.get('sort') or 'receipt_date').strip()
    sort_dir = (request.GET.get('dir') or 'desc').strip().lower()
    if sort_key not in _SORT_FIELDS:
        sort_key = 'receipt_date'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'
    orm_field = _SORT_FIELDS[sort_key]
    order = orm_field if sort_dir == 'asc' else f'-{orm_field}'
    return sort_key, sort_dir, order


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def receipt_list(request):
    search_query = get_search_query(request)
    status = _status_filter(request)
    sort_key, sort_dir, order = _list_sort(request)
    qs = StockReceipt.objects.select_related('warehouse', 'created_by', 'fg_receipt')
    if status:
        qs = qs.filter(status=status)
    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query)
            | Q(production_order_code__icontains=search_query)
            | Q(product_code__icontains=search_query)
            | Q(warehouse__code__icontains=search_query)
            | Q(warehouse__name__icontains=search_query)
            | Q(fg_receipt__code__icontains=search_query)
            | Q(notes__icontains=search_query)
        )
    qs = qs.annotate(qty_total=Sum('lines__quantity')).order_by(order, '-pk')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'kho_san_pham/receipt_list.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': RECEIPT_STATUS_FILTER_CHOICES,
        'has_filters': bool(search_query or status),
        'sort_key': sort_key,
        'sort_dir': sort_dir,
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        StockReceipt.objects.select_related(
            'warehouse', 'created_by', 'fg_receipt', 'fg_receipt__production_order',
        ).prefetch_related('lines__product'),
        pk=pk,
    )
    return render(request, 'kho_san_pham/receipt_detail.html', {
        **nav_context('receipts', user=request.user),
        **perm_context(request.user, 'receipts'),
        'receipt': receipt,
    })
