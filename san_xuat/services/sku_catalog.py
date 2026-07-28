"""SKU = Style + Màu + Size (vd. JP-TEE-260001-NVY-M).

Style neo theo product_code hồ sơ / lệnh SX. Catalog màu + size dùng chung;
ma trận SKU gắn từng Style.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from san_xuat.hub_models import SxColor, SxSize, SxSku

DEFAULT_COLORS: list[tuple[str, str, int]] = [
    ("NVY", "Navy", 10),
    ("BLK", "Đen", 20),
    ("WHT", "Trắng", 30),
    ("GRY", "Xám", 40),
    ("RED", "Đỏ", 50),
    ("BLU", "Xanh dương", 60),
    ("GRN", "Xanh lá", 70),
    ("BEG", "Be", 80),
]

DEFAULT_SIZES: list[tuple[str, str, int]] = [
    ("XS", "XS", 10),
    ("S", "S", 20),
    ("M", "M", 30),
    ("L", "L", 40),
    ("XL", "XL", 50),
    ("XXL", "XXL", 60),
    ("3XL", "3XL", 70),
]


class SkuError(Exception):
    pass


@dataclass(frozen=True)
class ResolvedSku:
    sku: SxSku | None
    sku_code: str
    style_code: str
    color_code: str
    color_label: str
    size_label: str


def normalize_token(value: str, *, max_len: int = 20) -> str:
    raw = (value or "").strip().upper()
    raw = re.sub(r"\s+", "", raw)
    raw = re.sub(r"[^A-Z0-9\-]", "", raw)
    return raw[:max_len]


def normalize_style(value: str) -> str:
    return (value or "").strip().upper()[:60]


def compose_sku_code(*, style_code: str, color_code: str = "", size_label: str) -> str:
    """Ghép SKU: ``{Style}-{Color}-{Size}`` hoặc ``{Style}-{Size}`` khi không có màu."""
    style = normalize_style(style_code)
    color = normalize_token(color_code) if color_code else ""
    size = normalize_token(size_label)
    if not style or not size:
        raise SkuError("Thiếu Style / size để ghép SKU.")
    code = f"{style}-{color}-{size}" if color else f"{style}-{size}"
    if len(code) > 100:
        raise SkuError("Mã SKU vượt quá 100 ký tự — rút ngắn Style/màu/size.")
    return code


def seed_default_colors_sizes() -> tuple[int, int]:
    c_created = 0
    for code, name, order in DEFAULT_COLORS:
        _, was = SxColor.objects.get_or_create(
            code=code,
            defaults={"name": name, "sort_order": order, "is_active": True, "is_demo": False},
        )
        if was:
            c_created += 1
    s_created = 0
    for code, name, order in DEFAULT_SIZES:
        _, was = SxSize.objects.get_or_create(
            code=code,
            defaults={"name": name, "sort_order": order, "is_active": True, "is_demo": False},
        )
        if was:
            s_created += 1
    return c_created, s_created


def color_choices(*, extra_code: str = "", blank_label: str = "— Chọn màu —") -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", blank_label)]
    seen: set[str] = set()
    for row in SxColor.objects.filter(is_active=True).order_by("sort_order", "code"):
        code = (row.code or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        choices.append((code, f"{code} — {row.name}"))
    extra = normalize_token(extra_code)
    if extra and extra not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def size_choices(*, extra_code: str = "", blank_label: str = "— Chọn size —") -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", blank_label)]
    seen: set[str] = set()
    for row in SxSize.objects.filter(is_active=True).order_by("sort_order", "code"):
        code = (row.code or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        label = (row.name or code).strip()
        choices.append((code, label if label == code else f"{code} — {label}"))
    extra = normalize_token(extra_code)
    if extra and extra not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def ensure_color(*, code: str, name: str = "", user=None) -> SxColor:
    code = normalize_token(code)
    if not code:
        raise SkuError("Mã màu trống.")
    existing = SxColor.objects.filter(code__iexact=code).first()
    if existing:
        fields: list[str] = []
        if not existing.is_active:
            existing.is_active = True
            fields.append("is_active")
        if name and (name or "").strip() and existing.name != (name or "").strip()[:80]:
            existing.name = (name or "").strip()[:80]
            fields.append("name")
        if fields:
            existing.save(update_fields=fields)
        return existing
    max_order = SxColor.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return SxColor.objects.create(
        code=code,
        name=(name or code).strip()[:80],
        sort_order=(max_order or 100) + 10,
        is_active=True,
        is_demo=False,
        created_by=user,
    )


def ensure_size(*, code: str, name: str = "", user=None) -> SxSize:
    code = normalize_token(code)
    if not code:
        raise SkuError("Size trống.")
    existing = SxSize.objects.filter(code__iexact=code).first()
    if existing:
        fields: list[str] = []
        if not existing.is_active:
            existing.is_active = True
            fields.append("is_active")
        if name and (name or "").strip() and existing.name != (name or "").strip()[:80]:
            existing.name = (name or "").strip()[:80]
            fields.append("name")
        if fields:
            existing.save(update_fields=fields)
        return existing
    max_order = SxSize.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return SxSize.objects.create(
        code=code,
        name=(name or code).strip()[:80],
        sort_order=(max_order or 100) + 10,
        is_active=True,
        is_demo=False,
        created_by=user,
    )


def update_color(
    *,
    color_id: int,
    name: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> SxColor:
    color = SxColor.objects.filter(pk=color_id).first()
    if not color:
        raise SkuError("Không tìm thấy màu.")
    fields: list[str] = []
    if name is not None:
        color.name = (name or color.code).strip()[:80]
        fields.append("name")
    if sort_order is not None:
        try:
            color.sort_order = max(0, int(sort_order))
        except (TypeError, ValueError) as exc:
            raise SkuError("Thứ tự màu không hợp lệ.") from exc
        fields.append("sort_order")
    if is_active is not None:
        color.is_active = bool(is_active)
        fields.append("is_active")
    if fields:
        color.save(update_fields=fields)
    return color


def update_size(
    *,
    size_id: int,
    name: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> SxSize:
    size = SxSize.objects.filter(pk=size_id).first()
    if not size:
        raise SkuError("Không tìm thấy size.")
    fields: list[str] = []
    if name is not None:
        size.name = (name or size.code).strip()[:80]
        fields.append("name")
    if sort_order is not None:
        try:
            size.sort_order = max(0, int(sort_order))
        except (TypeError, ValueError) as exc:
            raise SkuError("Thứ tự size không hợp lệ.") from exc
        fields.append("sort_order")
    if is_active is not None:
        size.is_active = bool(is_active)
        fields.append("is_active")
    if fields:
        size.save(update_fields=fields)
    return size


def color_label_for(code: str) -> str:
    code = normalize_token(code)
    if not code:
        return ""
    row = SxColor.objects.filter(code__iexact=code).first()
    return (row.name if row else "") or code


@transaction.atomic
def get_or_create_sku(
    *,
    style_code: str,
    color_code: str,
    size_label: str,
    color_label: str = "",
    style_name: str = "",
    sku_code: str = "",
    user=None,
    ensure_catalog: bool = True,
) -> SxSku:
    style = normalize_style(style_code)
    color = normalize_token(color_code) if color_code else ""
    size = normalize_token(size_label)
    if not style:
        raise SkuError("Thiếu Style (mã SP).")
    if not size:
        raise SkuError("SKU cần size.")

    if ensure_catalog:
        if color:
            ensure_color(code=color, name=color_label, user=user)
        ensure_size(code=size, user=user)

    label = (color_label or "").strip()
    if color:
        label = label or color_label_for(color)
    composed = (sku_code or "").strip().upper() or compose_sku_code(
        style_code=style, color_code=color, size_label=size,
    )

    existing = (
        SxSku.objects.filter(style_code__iexact=style, color_code__iexact=color, size_label__iexact=size).first()
        or SxSku.objects.filter(sku_code__iexact=composed).first()
    )
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if label and existing.color_label != label:
            existing.color_label = label[:80]
            changed = True
        if style_name and not existing.style_name:
            existing.style_name = style_name.strip()[:255]
            changed = True
        if changed:
            existing.save()
        return existing

    return SxSku.objects.create(
        style_code=style,
        style_name=(style_name or "").strip()[:255],
        color_code=color,
        color_label=label[:80],
        size_label=size,
        sku_code=composed,
        is_active=True,
        is_demo=False,
        created_by=user,
    )


def parse_sku_code(sku_code: str, *, style_hint: str = "") -> tuple[str, str, str] | None:
    """Tách STYLE-COLOR-SIZE hoặc STYLE-SIZE (color=''). Style có thể chứa '-'."""
    code = (sku_code or "").strip().upper()
    if not code:
        return None
    style_hint = normalize_style(style_hint)
    if style_hint and code.startswith(style_hint + "-"):
        rest = code[len(style_hint) + 1 :]
        if not rest:
            return None
        parts = rest.rsplit("-", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            # Có thể là COLOR-SIZE hoặc chỉ một đoạn SIZE nếu rest không có '-'
            return style_hint, parts[0], parts[1]
        return style_hint, "", rest
    parts = code.rsplit("-", 2)
    if len(parts) == 3 and all(parts):
        return parts[0], parts[1], parts[2]
    parts2 = code.rsplit("-", 1)
    if len(parts2) == 2 and all(parts2):
        return parts2[0], "", parts2[1]
    return None


def resolve_sku_fields(
    *,
    style_code: str,
    sku_code: str = "",
    color_code: str = "",
    color_label: str = "",
    size_label: str = "",
    style_name: str = "",
    user=None,
    create_if_missing: bool = True,
    require_complete: bool = False,
) -> ResolvedSku:
    """Chuẩn hoá SKU từ form. Ưu tiên: sku_code đã có → tách; else màu+size → ghép."""
    style = normalize_style(style_code)
    raw_sku = (sku_code or "").strip().upper()
    color = normalize_token(color_code)
    size = normalize_token(size_label)
    label = (color_label or "").strip()

    if raw_sku and (not color or not size):
        parsed = parse_sku_code(raw_sku, style_hint=style)
        if parsed:
            style = style or parsed[0]
            color = color or parsed[1]
            size = size or parsed[2]

    if not color and label:
        # Cho phép nhập tên màu → map mã nếu đã có catalog
        by_name = SxColor.objects.filter(name__iexact=label, is_active=True).first()
        if by_name:
            color = by_name.code
        else:
            # fallback: dùng chính label làm mã (chuẩn hoá)
            color = normalize_token(label)

    has_pair = bool(color and size)
    if require_complete and not has_pair and not raw_sku:
        raise SkuError("Cần chọn Màu và Size để tạo SKU (Style–Màu–Size).")

    if not has_pair and not raw_sku:
        return ResolvedSku(
            sku=None,
            sku_code="",
            style_code=style,
            color_code="",
            color_label=label,
            size_label="",
        )

    if not create_if_missing:
        if raw_sku:
            sku = SxSku.objects.filter(sku_code__iexact=raw_sku).first()
            if sku:
                return ResolvedSku(
                    sku=sku,
                    sku_code=sku.sku_code,
                    style_code=sku.style_code,
                    color_code=sku.color_code,
                    color_label=sku.color_label,
                    size_label=sku.size_label,
                )
        if style and color and size:
            sku = SxSku.objects.filter(
                style_code__iexact=style, color_code__iexact=color, size_label__iexact=size,
            ).first()
            if sku:
                return ResolvedSku(
                    sku=sku,
                    sku_code=sku.sku_code,
                    style_code=sku.style_code,
                    color_code=sku.color_code,
                    color_label=sku.color_label,
                    size_label=sku.size_label,
                )
        composed = raw_sku or (
            compose_sku_code(style_code=style, color_code=color, size_label=size)
            if style and color and size else ""
        )
        return ResolvedSku(
            sku=None,
            sku_code=composed,
            style_code=style,
            color_code=color,
            color_label=label or color_label_for(color),
            size_label=size,
        )

    sku = get_or_create_sku(
        style_code=style,
        color_code=color,
        size_label=size,
        color_label=label,
        style_name=style_name,
        sku_code=raw_sku,
        user=user,
    )
    return ResolvedSku(
        sku=sku,
        sku_code=sku.sku_code,
        style_code=sku.style_code,
        color_code=sku.color_code,
        color_label=sku.color_label,
        size_label=sku.size_label,
    )


@transaction.atomic
def expand_style_matrix(
    *,
    style_code: str,
    color_codes: list[str],
    size_labels: list[str],
    style_name: str = "",
    user=None,
) -> list[SxSku]:
    style = normalize_style(style_code)
    if not style:
        raise SkuError("Thiếu Style.")
    colors = [normalize_token(c) for c in color_codes if normalize_token(c)]
    sizes = [normalize_token(s) for s in size_labels if normalize_token(s)]
    if not colors or not sizes:
        raise SkuError("Cần ít nhất 1 màu và 1 size để tạo danh sách SKU.")
    created: list[SxSku] = []
    for color in colors:
        for size in sizes:
            created.append(
                get_or_create_sku(
                    style_code=style,
                    color_code=color,
                    size_label=size,
                    style_name=style_name,
                    user=user,
                )
            )
    return created


def skus_for_style(style_code: str, *, active_only: bool = True):
    style = normalize_style(style_code)
    qs = SxSku.objects.filter(style_code__iexact=style)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("color_code", "size_label")


@transaction.atomic
def delete_sku(*, sku_id: int | str | None = None, style_code: str = "") -> SxSku:
    """Xóa SKU khỏi danh sách Style. FK liên quan (TKSX/QC/đóng gói/YCNTP) SET_NULL."""
    style = normalize_style(style_code)
    try:
        pk = int(sku_id) if sku_id is not None and str(sku_id).strip() != "" else None
    except (TypeError, ValueError) as exc:
        raise SkuError("SKU không hợp lệ.") from exc
    if pk is None:
        raise SkuError("Thiếu SKU cần xóa.")
    sku = SxSku.objects.filter(pk=pk).first()
    if sku is None:
        raise SkuError("Không tìm thấy SKU.")
    if style and sku.style_code.upper() != style:
        raise SkuError(f"SKU {sku.sku_code} không thuộc Style {style}.")
    code = sku.sku_code
    sku.delete()
    # Return a detached stub for messaging (pk cleared after delete).
    sku.sku_code = code
    return sku


def search_skus(*, q: str = "", style_code: str = "", limit: int = 30) -> list[dict]:
    qs = SxSku.objects.filter(is_active=True)
    style = normalize_style(style_code)
    if style:
        qs = qs.filter(style_code__iexact=style)
    q = (q or "").strip()
    if q:
        qs = qs.filter(
            Q(sku_code__icontains=q)
            | Q(color_code__icontains=q)
            | Q(color_label__icontains=q)
            | Q(size_label__icontains=q)
            | Q(style_code__icontains=q)
        )
    rows = []
    for sku in qs.order_by("sku_code")[: max(1, min(limit, 100))]:
        rows.append({
            "id": sku.sku_code,
            "sku_code": sku.sku_code,
            "style_code": sku.style_code,
            "color_code": sku.color_code,
            "color_label": sku.color_label,
            "size_label": sku.size_label,
            "text": f"{sku.sku_code} · {sku.color_label or sku.color_code}/{sku.size_label}",
        })
    return rows


def sku_has_identity(*, sku_code: str = "", color_code: str = "", size_label: str = "") -> bool:
    if (sku_code or "").strip():
        return True
    return bool(normalize_token(color_code) and normalize_token(size_label))
