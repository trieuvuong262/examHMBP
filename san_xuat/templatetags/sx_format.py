"""Bộ lọc hiển thị số liệu Sản xuất (nguyên mặc định, có lẻ mới hiện)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _vn_group_int(n: int) -> str:
    sign = "-" if n < 0 else ""
    return sign + f"{abs(n):,}".replace(",", ".")


def format_sx_num(value, max_decimals: int = 4) -> str:
    """Số nguyên khi hết phần lẻ; có lẻ thì hiện (dấu phẩy VN, nghìn = dấu chấm)."""
    d = _to_decimal(value)
    if d is None:
        return "—"
    if max_decimals < 0:
        max_decimals = 0
    quantized = d.quantize(Decimal(10) ** -max_decimals, rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return _vn_group_int(int(quantized))
    text = f"{quantized:.{max_decimals}f}".rstrip("0").rstrip(".")
    neg = text.startswith("-")
    if neg:
        text = text[1:]
    if "." in text:
        whole, frac = text.split(".", 1)
        return f"{'-' if neg else ''}{_vn_group_int(int(whole))},{frac}"
    return f"{'-' if neg else ''}{_vn_group_int(int(text))}"


def format_sx_num_input(value, max_decimals: int = 4) -> str:
    """Số gọn cho value= input (dấu chấm thập phân, không nhóm nghìn)."""
    d = _to_decimal(value)
    if d is None:
        return ""
    if max_decimals < 0:
        max_decimals = 0
    quantized = d.quantize(Decimal(10) ** -max_decimals, rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    return f"{quantized:.{max_decimals}f}".rstrip("0").rstrip(".") or "0"


@register.filter(name="sx_num")
def sx_num(value, max_decimals=4):
    try:
        decimals = int(max_decimals)
    except (TypeError, ValueError):
        decimals = 4
    return format_sx_num(value, decimals)


@register.filter(name="sx_num_input")
def sx_num_input(value, max_decimals=4):
    try:
        decimals = int(max_decimals)
    except (TypeError, ValueError):
        decimals = 4
    return format_sx_num_input(value, decimals)


@register.filter(name="sx_req_star")
def sx_req_star(bound_field):
    """Append red * when a BoundField is required (for form labels)."""
    from django.utils.safestring import mark_safe

    field = getattr(bound_field, "field", None)
    if field is not None and getattr(field, "required", False):
        return mark_safe(' <span class="text-danger">*</span>')
    return ""


_AUDIT_RESERVED_KEYS = {"fields", "lines", "snapshot"}

# Bản ghi nhật ký cũ lưu tên trường thô — đổi sang nhãn tiếng Việt khi hiển thị.
_AUDIT_LEGACY_LABELS = {
    "n_lines": "Số dòng NPL",
    "version_label": "Phiên bản",
    "overhead_pct": "Phụ phí (%)",
    "overhead_amount": "SX chung / SP",
    "notes": "Ghi chú",
    "op_code": "Mã công đoạn",
    "op_name": "Tên công đoạn",
    "op_name_vi": "Tên công đoạn",
    "group_code": "Nhóm công đoạn",
    "work_center_code": "Bộ phận",
}


@register.filter(name="sx_audit_detail")
def sx_audit_detail(changes):
    """Chuẩn hóa `changes` của nhật ký BOM/OB về một cấu trúc để render.

    Hỗ trợ cả bản ghi cũ (dict phẳng tên_trường → {before, after}) lẫn bản ghi
    mới (có khóa `fields` / `lines` / `snapshot`).
    """
    if not isinstance(changes, dict):
        return {"fields": [], "added": [], "removed": [], "changed": [], "has_snapshot": False}

    def as_pairs(mapping):
        pairs = []
        for key, val in (mapping or {}).items():
            label = _AUDIT_LEGACY_LABELS.get(key, key)
            if isinstance(val, dict):
                pairs.append({
                    "label": label,
                    "before": val.get("before", "—"),
                    "after": val.get("after", "—"),
                })
            else:
                pairs.append({"label": label, "before": "—", "after": val})
        return pairs

    fields = as_pairs(changes.get("fields"))
    if not fields:
        legacy = {k: v for k, v in changes.items() if k not in _AUDIT_RESERVED_KEYS}
        fields = as_pairs(legacy)

    lines = changes.get("lines") or {}
    return {
        "fields": fields,
        "added": lines.get("added") or [],
        "removed": lines.get("removed") or [],
        "changed": lines.get("changed") or [],
        "has_snapshot": bool(changes.get("snapshot")),
        "snapshot_count": len((changes.get("snapshot") or {}).get("lines") or []),
    }
