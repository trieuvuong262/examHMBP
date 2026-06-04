from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .access import kiotviet_is_live, user_can_use_kiotviet
from .client import KiotVietAPIError, KiotVietClient


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not kiotviet_is_live():
            messages.error(
                request,
                'KiotViet chưa được cấu hình trên server (.env: KIOTVIET_ENABLED=1 và Client ID/Secret/Retailer).',
            )
            return redirect('home_portal')
        if not user_can_use_kiotviet(request.user):
            messages.error(request, 'Bạn không có quyền truy cập module KiotViet.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)

    return wrapper


def _format_customer_row(row: dict) -> dict:
    gender = row.get('gender')
    if gender is True:
        gender_label = 'Nam'
    elif gender is False:
        gender_label = 'Nữ'
    else:
        gender_label = '—'
    return {
        'id': row.get('id'),
        'code': row.get('code') or '—',
        'name': row.get('name') or '—',
        'contact_number': row.get('contactNumber') or '—',
        'email': row.get('email') or '—',
        'address': row.get('address') or '—',
        'debt': row.get('debt'),
        'total_revenue': row.get('totalRevenue'),
        'reward_point': row.get('rewardPoint'),
        'gender_label': gender_label,
        'modified_date': row.get('modifiedDate'),
    }


@_access_required
def customer_lookup(request):
    search_type = (request.GET.get('type') or 'name').strip()
    if search_type not in ('name', 'code', 'phone'):
        search_type = 'name'
    query = get_search_query(request)
    customers: list[dict] = []
    total = None
    api_error = None

    if query:
        client = KiotVietClient()
        params = {
            'pageSize': 50,
            'currentItem': 0,
            'orderBy': 'name',
            'orderDirection': 'Asc',
            'includeTotal': 'true',
        }
        if search_type == 'code':
            params['code'] = query
        elif search_type == 'phone':
            params['contactNumber'] = query
        else:
            params['name'] = query

        try:
            if search_type == 'code' and len(query) <= 64:
                try:
                    detail = client.get_customer_by_code(query)
                    customers = [_format_customer_row(detail)]
                    total = 1
                except KiotVietAPIError as exc:
                    if exc.status_code != 404:
                        raise
                    payload = client.list_customers(**params)
                    rows = payload.get('data') or []
                    customers = [_format_customer_row(r) for r in rows]
                    total = payload.get('total', len(customers))
            else:
                payload = client.list_customers(**params)
                rows = payload.get('data') or []
                customers = [_format_customer_row(r) for r in rows]
                total = payload.get('total', len(customers))
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/customer_lookup.html',
        {
            'search_type': search_type,
            'search_query': query,
            'customers': customers,
            'total': total,
            'api_error': api_error,
            'retailer': KiotVietClient().retailer if KiotVietClient.is_configured() else '',
        },
    )


@_access_required
def customer_detail(request, customer_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_customer(customer_id)
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
        return redirect('kiotviet:customer_lookup')

    customer = _format_customer_row(raw)
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
