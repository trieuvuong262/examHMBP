from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import fetch_api_page, get_page_number, paginate_api_meta
from .client import KiotVietAPIError, KiotVietClient
from .decorators import kiotviet_access_required
from .formatters import format_customer_row


@kiotviet_access_required
def customer_lookup(request):
    search_type = (request.GET.get('type') or 'name').strip()
    if search_type not in ('name', 'code', 'phone'):
        search_type = 'name'
    query = get_search_query(request)
    customers: list[dict] = []
    total = 0
    api_error = None
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)

    client = KiotVietClient()
    base_params = {
        'orderBy': 'name',
        'orderDirection': 'Asc',
        'includeTotal': 'true',
    }

    try:
        if browse_mode:
            rows, total = fetch_api_page(client.list_customers, base_params, page)
            customers = [format_customer_row(r) for r in rows]
        elif search_type == 'code' and len(query) <= 64:
            try:
                detail = client.get_customer_by_code(query)
                customers = [format_customer_row(detail)]
                total = 1
            except KiotVietAPIError as exc:
                if exc.status_code != 404:
                    raise
                params = {**base_params, 'code': query}
                rows, total = fetch_api_page(client.list_customers, params, page)
                customers = [format_customer_row(r) for r in rows]
        else:
            params = dict(base_params)
            if search_type == 'phone':
                params['contactNumber'] = query
            else:
                params['name'] = query
            rows, total = fetch_api_page(client.list_customers, params, page)
            customers = [format_customer_row(r) for r in rows]
    except KiotVietAPIError as exc:
        api_error = str(exc)
        messages.error(request, api_error)

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
            'api_error': api_error,
            'page_obj': page_obj,
            'query_string': query_string,
            'browse_mode': browse_mode,
            'retailer': client.retailer if KiotVietClient.is_configured() else '',
        },
    )


@kiotviet_access_required
def customer_detail(request, customer_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_customer(customer_id)
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
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
