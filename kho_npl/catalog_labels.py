"""Nhãn hiển thị danh mục kho NPL — luôn ưu tiên tên, không dùng mã trên giao diện."""


def catalog_label(obj) -> str:
    if obj is None:
        return ''
    name = getattr(obj, 'name', None)
    code = getattr(obj, 'code', None)
    return (name or code or str(obj)).strip()


def unit_label(unit) -> str:
    return catalog_label(unit)


def spec_label(spec) -> str:
    return catalog_label(spec)


def color_label(color) -> str:
    return catalog_label(color)
