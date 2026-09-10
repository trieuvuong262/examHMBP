"""Nhu cầu NPL = định mức BOM đã chọn × số lượng (theo size nếu BOM có size)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from san_xuat.hub_models import SxProductionOrder, SxSalesOrderLine


def _q(val, default: str = '0') -> Decimal:
    try:
        return Decimal(str(val if val is not None else default))
    except Exception:
        return Decimal(default)


def _size_key(raw) -> str:
    return str(raw or '').strip().casefold()


def size_qty_map(raw) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        qty = _q(val)
        if qty <= 0:
            continue
        out[_size_key(key)] = out.get(_size_key(key), Decimal('0')) + qty
    return out


def scale_qty(*, size_code: str, line_qty: Decimal, size_qtys: dict | None) -> Decimal:
    """SL nhân định mức: BOM mọi size → SL dòng; BOM theo size → SL size đó."""
    total = _q(line_qty)
    size = (size_code or '').strip()
    mapped = size_qty_map(size_qtys)
    if not size:
        return total
    hit = mapped.get(_size_key(size))
    if hit is not None:
        return hit
    if not mapped:
        return total
    return Decimal('0')


def per_unit_with_scrap(qty, scrap_pct) -> Decimal:
    factor = Decimal('1') + _q(scrap_pct) / Decimal('100')
    return (_q(qty) * factor).quantize(Decimal('0.0001'))


def _unit_display(unit) -> str:
    """Nhãn ĐVT trên giao diện: tên, không dùng mã."""
    from kho_npl.catalog_labels import unit_label

    return (unit_label(unit) or '')[:30]


@dataclass(frozen=True)
class MaterialNeed:
    material_code: str
    material_name: str
    qty_per_unit: Decimal
    qty_total: Decimal
    scrap_pct: Decimal
    size_code: str = ''
    unit: str = ''
    bom_line_id: int | None = None
    scale_qty: Decimal = Decimal('0')


def explode_overrides(
    *,
    overrides: list | None,
    qty: Decimal,
    size_qtys: dict | None = None,
) -> list[MaterialNeed]:
    rows: list[MaterialNeed] = []
    for raw in overrides or []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get('material_code') or '').strip()
        name = str(raw.get('material_name') or '').strip()
        try:
            bom_line_id = int(raw.get('bom_line_id') or raw.get('id') or 0) or None
        except (TypeError, ValueError):
            bom_line_id = None
        if not code and not name and not bom_line_id:
            continue
        bl = None
        if bom_line_id and not code:
            from san_xuat.models import BomLine

            bl = (
                BomLine.objects.select_related('material', 'material__unit')
                .filter(pk=bom_line_id)
                .first()
            )
            if bl is not None and bl.material_id:
                code = (bl.material.code or '').strip()
                name = name or (bl.material.name or '').strip()
        size_code = str(raw.get('size_code') or '').strip()
        scrap = _q(raw.get('scrap_pct'))
        per = per_unit_with_scrap(raw.get('qty'), scrap)
        scale = scale_qty(size_code=size_code, line_qty=qty, size_qtys=size_qtys)
        total = (per * scale).quantize(Decimal('0.001'))
        if total <= 0 and per <= 0:
            continue
        unit = str(raw.get('unit') or '')[:30]
        if bl is not None and getattr(bl, 'material_id', None) and bl.material.unit_id:
            unit = _unit_display(bl.material.unit)
        rows.append(
            MaterialNeed(
                material_code=code[:60],
                material_name=(name or code)[:255],
                qty_per_unit=per,
                qty_total=total,
                scrap_pct=scrap,
                size_code=size_code[:20],
                unit=unit,
                bom_line_id=bom_line_id,
                scale_qty=scale,
            )
        )
    return rows


def explode_bom(
    *,
    bom,
    qty: Decimal,
    size_qtys: dict | None = None,
) -> list[MaterialNeed]:
    if bom is None:
        return []
    rows: list[MaterialNeed] = []
    lines = bom.lines.select_related('material', 'material__unit', 'substitute_material').all()
    for bl in lines:
        mat = bl.material
        if mat is None:
            continue
        size_code = (bl.size_code or '').strip()
        per = bl.qty_with_scrap
        scale = scale_qty(size_code=size_code, line_qty=qty, size_qtys=size_qtys)
        total = (per * scale).quantize(Decimal('0.001'))
        unit = _unit_display(mat.unit) if mat.unit_id else ''
        rows.append(
            MaterialNeed(
                material_code=(mat.code or '')[:60],
                material_name=(mat.name or mat.code or '')[:255],
                qty_per_unit=per,
                qty_total=total,
                scrap_pct=_q(bl.scrap_pct),
                size_code=size_code[:20],
                unit=unit,
                bom_line_id=bl.pk,
                scale_qty=scale,
            )
        )
    return rows


def sales_line_for_mo(mo: SxProductionOrder) -> SxSalesOrderLine | None:
    if not mo.sales_order_id:
        return None
    product = (mo.product_code or '').strip().casefold()
    lines = list(mo.sales_order.lines.all())
    for ln in lines:
        if product and (ln.product_code or '').strip().casefold() == product:
            return ln
    return lines[0] if lines else None


def size_qtys_for_mo(mo: SxProductionOrder, so_line: SxSalesOrderLine | None = None) -> dict:
    if so_line is not None and so_line.size_qtys:
        return so_line.size_qtys
    labeled: dict[str, Decimal] = {}
    for ln in mo.lines.all():
        sz = (ln.size_label or '').strip()
        if not sz:
            continue
        labeled[sz] = labeled.get(sz, Decimal('0')) + _q(ln.qty)
    return labeled


def explode_for_sales_line(line: SxSalesOrderLine) -> list[MaterialNeed]:
    qty = line.qty_to_produce
    sizes = line.size_qtys or {}
    overrides = list(line.bom_line_overrides or [])
    if overrides:
        return explode_overrides(overrides=overrides, qty=qty, size_qtys=sizes)
    return explode_bom(bom=line.bom_version, qty=qty, size_qtys=sizes)


def explode_for_mo(mo: SxProductionOrder, *, qty: Decimal | None = None) -> list[MaterialNeed]:
    so_line = sales_line_for_mo(mo)
    scale = _q(qty if qty is not None else mo.qty)
    sizes = size_qtys_for_mo(mo, so_line)
    so_sizes = (so_line.size_qtys if so_line is not None else None) or sizes
    if so_line is not None:
        if so_line.bom_line_overrides:
            rows = explode_overrides(
                overrides=so_line.bom_line_overrides,
                qty=scale,
                size_qtys=so_sizes,
            )
            if any(r.qty_total > 0 for r in rows):
                return rows
        if so_line.bom_version_id:
            return explode_bom(bom=so_line.bom_version, qty=scale, size_qtys=so_sizes)
    return explode_bom(bom=mo.bom_version, qty=scale, size_qtys=sizes)


def sales_line_with_bom(product_code: str) -> SxSalesOrderLine | None:
    """Dòng ĐĐH đã xác nhận gần nhất còn BOM / ĐM áp dụng."""
    from san_xuat.hub_models import SxSalesOrder

    code = (product_code or '').strip()
    if not code:
        return None
    rows = (
        SxSalesOrderLine.objects.filter(
            product_code__iexact=code,
            order__is_demo=False,
            order__confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        .select_related('bom_version')
        .order_by('-order_id', '-id')[:20]
    )
    for ln in rows:
        if ln.bom_line_overrides or ln.bom_version_id:
            return ln
    return None


def explode_for_product(
    *,
    product_code: str,
    qty: Decimal,
    size_qtys: dict | None = None,
) -> list[MaterialNeed]:
    """Nhu cầu NPL theo BOM đã chọn trên đơn; không có thì mới lấy BOM active hồ sơ."""
    line = sales_line_with_bom(product_code)
    if line is not None:
        if line.bom_line_overrides:
            return explode_overrides(
                overrides=line.bom_line_overrides,
                qty=qty,
                size_qtys=size_qtys,
            )
        if line.bom_version_id:
            return explode_bom(bom=line.bom_version, qty=qty, size_qtys=size_qtys)
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.bom import get_active_bom

    doc = ProductTechDoc.objects.filter(product_code__iexact=product_code, is_active=True).first()
    if doc is None:
        return []
    return explode_bom(bom=get_active_bom(doc), qty=qty, size_qtys=size_qtys)


def resolve_issue_material(need: MaterialNeed):
    from kho_npl.models import Material
    from san_xuat.models import BomLine

    if need.bom_line_id:
        bl = (
            BomLine.objects.select_related('material', 'substitute_material')
            .filter(pk=need.bom_line_id)
            .first()
        )
        if bl is not None:
            return bl.resolve_issue_material(needed_qty=need.qty_total)
    code = (need.material_code or '').strip()
    if not code:
        return None
    return Material.objects.filter(code__iexact=code).first()


def needs_as_display_dicts(rows: list[MaterialNeed]) -> list[dict]:
    from django.db.models.functions import Lower

    from kho_npl.models import Material, Unit

    codes = {(r.material_code or '').strip() for r in rows if (r.material_code or '').strip()}
    image_by_code: dict[str, str] = {}
    unit_by_mat: dict[str, str] = {}
    if codes:
        folded = {c.casefold() for c in codes}
        materials = (
            Material.objects.select_related('unit')
            .annotate(_code_l=Lower('code'))
            .filter(_code_l__in=folded)
        )
        for material in materials:
            key = (material.code or '').strip().casefold()
            try:
                url = material.image.url if material.image else ''
            except (ValueError, OSError):
                url = ''
            if url:
                image_by_code[key] = url
            if material.unit_id:
                unit_by_mat[key] = _unit_display(material.unit)
    leftover = {
        (r.unit or '').strip()
        for r in rows
        if (r.unit or '').strip()
        and not unit_by_mat.get((r.material_code or '').strip().casefold())
    }
    unit_by_code: dict[str, str] = {}
    if leftover:
        folded_units = {u.casefold() for u in leftover}
        for unit in Unit.objects.filter(code__in=folded_units):
            unit_by_code[(unit.code or '').casefold()] = _unit_display(unit)

    def _display_unit(row: MaterialNeed) -> str:
        key = (row.material_code or '').strip().casefold()
        if unit_by_mat.get(key):
            return unit_by_mat[key]
        stored = (row.unit or '').strip()
        if stored:
            return unit_by_code.get(stored.casefold()) or stored
        return ''

    return [
        {
            'material_code': r.material_code,
            'material_name': r.material_name,
            'qty_per_unit': r.qty_per_unit,
            'qty_total': r.qty_total,
            'scrap_pct': r.scrap_pct,
            'size_code': r.size_code,
            'unit': _display_unit(r),
            'scale_qty': r.scale_qty,
            'image_url': image_by_code.get((r.material_code or '').strip().casefold(), ''),
        }
        for r in rows
    ]
