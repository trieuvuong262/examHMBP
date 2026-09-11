"""Nhãn hiển thị danh mục kho NPL — luôn ưu tiên tên, không dùng mã trên giao diện."""


def catalog_label(obj) -> str:
    if obj is None:
        return ''
    name = getattr(obj, 'name', None)
    code = getattr(obj, 'code', None)
    return (name or code or str(obj)).strip()


def _unit_label_map() -> dict[str, str]:
    """code/name (casefold) → tên ĐVT. Cache theo request GET."""
    from hrm.request_cache import get_or_set
    from kho_npl.models import Unit

    def _load():
        out: dict[str, str] = {}
        for unit in Unit.objects.all().only('code', 'name'):
            label = catalog_label(unit)
            if not label:
                continue
            if unit.code:
                out[unit.code.casefold()] = label
            if unit.name:
                out[unit.name.casefold()] = label
        return out

    return get_or_set(('kho_npl_unit_labels',), _load)


def unit_label(unit) -> str:
    """Tên ĐVT để hiện trên UI. Chuỗi mã (met, cai, …) được đổi sang tên."""
    if unit is None or unit == '':
        return ''
    if isinstance(unit, str):
        text = unit.strip()
        if not text:
            return ''
        return _unit_label_map().get(text.casefold()) or text
    return catalog_label(unit)


def spec_label(spec) -> str:
    return catalog_label(spec)


def color_label(color) -> str:
    return catalog_label(color)
