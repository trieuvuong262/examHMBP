from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import KV_PAGE_SIZE, get_page_number, paginate_api_meta
from .decorators import kiotviet_access_required
from .formatters import format_customer_row
from . import local_lookup as local
from .sync_service import current_retailer

MIRROR_EMPTY_HINT = (
    'Chưa có dữ liệu mirror. Vào Quản Trị Hệ thống → Đồng bộ KiotViet để sync.'
)


@kiotviet_access_required
def customer_lookup(request):
    search_type = (request.GET.get('type') or 'name').strip()
    if search_type not in ('name', 'code', 'phone'):
        search_type = 'name'
    query = get_search_query(request)
    customers: list[dict] = []
    total = 0
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)
    retailer = current_retailer()

    if browse_mode:
        rows, total = local.browse_customers(page=page, per_page=KV_PAGE_SIZE, retailer=retailer)
    elif search_type == 'code' and len(query) <= 64:
        detail = local.get_customer_by_code(retailer, query)
        if detail:
            rows, total = [detail], 1
        else:
            rows, total = local.browse_customers(
                page=page, per_page=KV_PAGE_SIZE, code=query, retailer=retailer,
            )
    else:
        rows, total = local.browse_customers(
            page=page,
            per_page=KV_PAGE_SIZE,
            name=query if search_type != 'phone' else '',
            contact_number=query if search_type == 'phone' else '',
            retailer=retailer,
        )
    customers = [format_customer_row(r) for r in rows]

    if total and (browse_mode or query):
        page_obj, query_string = paginate_api_meta(request, total)

    return render(
        request,
        'kiotviet/customer_lookup.html',
        {
            'search_type': search_type,
            'search_query': query,
            'customers': customers,
            'total': total,
            'api_error': None,
            'mirror_empty_hint': MIRROR_EMPTY_HINT if total == 0 else '',
            'page_obj': page_obj,
            'query_string': query_string,
            'browse_mode': browse_mode,
            'retailer': retailer,
        },
    )


@kiotviet_access_required
def customer_detail(request, customer_id: int):
    retailer = current_retailer()
    raw = local.get_customer(retailer, customer_id)
    if raw is None:
        messages.error(request, 'Không tìm thấy khách hàng trong dữ liệu đã sync.')
        return redirect('kiotviet:customer_lookup')

    customer = format_customer_row(raw)
    customer.update(
        {
            'organization': raw.get('organization') or '—',
            'comments': raw.get('comments') or '—',
            'tax_code': raw.get('taxCode') or '—',
            'location_name': raw.get('locationName') or '—',
            'birth_date': raw.get('birthDate'),
            'created_date': raw.get('createdDate'),
            'total_invoiced': raw.get('totalInvoiced'),
            'total_point': raw.get('totalPoint'),
            'groups': raw.get('groups') or '—',
        }
    )
    return render(request, 'kiotviet/customer_detail.html', {'customer': customer})
