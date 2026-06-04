"""Danh sách mặc định & phân trang qua API KiotViet (pageSize / currentItem)."""

from __future__ import annotations

from typing import Any, Callable

from django.core.paginator import Paginator

from PortalJustPlay.pagination import LIST_PAGE_SIZE

KV_PAGE_SIZE = LIST_PAGE_SIZE


def get_page_number(request, *, param: str = 'page') -> int:
    try:
        return max(1, int(request.GET.get(param) or 1))
    except (TypeError, ValueError):
        return 1


def api_current_item(page: int, *, per_page: int = KV_PAGE_SIZE) -> int:
    return (page - 1) * per_page


def paginate_api_meta(
    request,
    total: int,
    *,
    page_param: str = 'page',
    per_page: int = KV_PAGE_SIZE,
):
    """page_obj Django + query_string (không gồm tham số trang) cho template pagination."""
    total = max(int(total or 0), 0)
    paginator = Paginator(range(total), per_page) if total else Paginator([], per_page)
    page_obj = paginator.get_page(request.GET.get(page_param))
    params = request.GET.copy()
    if page_param in params:
        del params[page_param]
    return page_obj, params.urlencode()


def fetch_api_page(
    list_fn: Callable[..., dict],
    base_params: dict[str, Any],
    page: int,
    *,
    per_page: int = KV_PAGE_SIZE,
) -> tuple[list[dict], int]:
    params = {k: v for k, v in base_params.items() if v not in (None, '')}
    params['pageSize'] = per_page
    params['currentItem'] = api_current_item(page, per_page=per_page)
    payload = list_fn(**params)
    rows = payload.get('data') or []
    total = payload.get('total')
    if total is None:
        total = len(rows)
    return rows, int(total)


def paginate_list_items(
    request,
    items: list,
    *,
    page_param: str = 'page',
    per_page: int = KV_PAGE_SIZE,
):
    """Phân trang danh sách đã lọc phía server (barcode, mã phiếu…)."""
    paginator = Paginator(items, per_page)
    page_obj = paginator.get_page(request.GET.get(page_param))
    params = request.GET.copy()
    if page_param in params:
        del params[page_param]
    return page_obj.object_list, page_obj, params.urlencode()
