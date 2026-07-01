"""Tiện ích parse bộ lọc GET (nhiều kho / nhiều nhóm)."""


def parse_int_ids(request, param: str) -> list[int]:
    """Đọc danh sách ID từ ?param=1&param=2 hoặc ?param=1 (tương thích cũ)."""
    if hasattr(request, 'GET'):
        values = request.GET.getlist(param)
        if not values:
            single = (request.GET.get(param) or '').strip()
            if single:
                values = [single]
    else:
        values = []
    ids: list[int] = []
    seen: set[int] = set()
    for raw in values:
        text = str(raw).strip()
        if text.isdigit():
            pk = int(text)
            if pk not in seen:
                seen.add(pk)
                ids.append(pk)
    return ids


def append_filter_params(
    params: list[str],
    *,
    locations: list[int] | None = None,
    categories: list[int] | None = None,
    category_parent: int | None = None,
):
    for loc_id in locations or []:
        params.append(f'location={loc_id}')
    if category_parent:
        params.append(f'category_parent={category_parent}')
    for cat_id in categories or []:
        params.append(f'category={cat_id}')


def append_wh_params(params: list[str], warehouse_ids: list[int] | None = None):
    for wh_id in warehouse_ids or []:
        params.append(f'wh={wh_id}')
