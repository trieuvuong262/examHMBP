"""Báo cáo xuất nhập tồn — tổng hợp theo mã hàng trên sổ kho."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from kho_npl.material_search import apply_material_search
from kho_npl.models import Material, StockLedger
from kho_npl.services.scrap_warehouse import exclude_scrap_locations, source_locations_qs
from kho_npl.services.variant_groups import group_xnt_rows

DISPLAY_LIMIT = 2000

QTY_FIELD = DecimalField(max_digits=14, decimal_places=3)
AMT_FIELD = DecimalField(max_digits=16, decimal_places=2)
ZERO_QTY = Value(Decimal('0.000'), output_field=QTY_FIELD)
ZERO_AMT = Value(Decimal('0.00'), output_field=AMT_FIELD)

XNT_COLUMNS = [
    ('group_name', 'Tên nhóm hàng'),
    ('code', 'Mã hàng'),
    ('name', 'Tên hàng'),
    ('qty_open', 'Tồn đầu kỳ'),
    ('val_open', 'Giá trị đầu kỳ'),
    ('qty_in', 'SL Nhập'),
    ('val_in', 'Giá trị nhập'),
    ('qty_out', 'SL Xuất'),
    ('val_out', 'Giá trị xuất'),
    ('qty_close', 'Tồn cuối kỳ'),
    ('val_close', 'Giá trị cuối kỳ'),
]


def _parse_date(value: str | None, default: date | None = None) -> date | None:
    raw = (value or '').strip()
    if not raw:
        return default
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return default


def _period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def _ledger_qs(location_id: int | None = None):
    qs = StockLedger.objects.all()
    if location_id:
        return qs.filter(location_id=location_id)
    return exclude_scrap_locations(qs)


def _signed_amount():
    return Case(
        When(qty_delta__lt=0, then=-F('amount')),
        default=F('amount'),
        output_field=AMT_FIELD,
    )


def _qty_in():
    return Case(
        When(qty_delta__gt=0, then=F('qty_delta')),
        default=ZERO_QTY,
        output_field=QTY_FIELD,
    )


def _qty_out():
    return Case(
        When(qty_delta__lt=0, then=-F('qty_delta')),
        default=ZERO_QTY,
        output_field=QTY_FIELD,
    )


def _val_in():
    return Case(
        When(qty_delta__gt=0, then=F('amount')),
        default=ZERO_AMT,
        output_field=AMT_FIELD,
    )


def _val_out():
    return Case(
        When(qty_delta__lt=0, then=F('amount')),
        default=ZERO_AMT,
        output_field=AMT_FIELD,
    )


def _as_map(rows, keys: tuple[str, ...]) -> dict[int, dict]:
    out = {}
    for row in rows:
        mid = row['material_id']
        out[mid] = {key: row.get(key) or Decimal('0') for key in keys}
    return out


def _zero_totals() -> dict:
    return {
        'qty_open': Decimal('0'),
        'val_open': Decimal('0'),
        'qty_in': Decimal('0'),
        'val_in': Decimal('0'),
        'qty_out': Decimal('0'),
        'val_out': Decimal('0'),
        'qty_close': Decimal('0'),
        'val_close': Decimal('0'),
    }


def _add_totals(totals: dict, row: dict) -> None:
    for key in totals:
        totals[key] += row[key]


def location_scope_label(location_id: int | None) -> str:
    if not location_id:
        return 'Toàn bộ kho'
    loc = source_locations_qs().filter(pk=location_id).first()
    return loc.display_label() if loc else 'Toàn bộ kho'


def report_xuat_nhap_ton(
    date_from: date,
    date_to: date,
    *,
    location_id: int | None = None,
    search: str = '',
    limit: int | None = DISPLAY_LIMIT,
) -> dict:
    """Tồn đầu kỳ + nhập − xuất = tồn cuối kỳ, theo từng mã NPL."""
    start, end = _period_bounds(date_from, date_to)
    qs = _ledger_qs(location_id)

    opening_qs = qs.filter(created_at__lt=start)
    period_qs = qs.filter(created_at__gte=start, created_at__lt=end)
    if not location_id:
        # Chuyển kho nội bộ không đổi tổng tồn khi xem toàn bộ kho.
        period_qs = period_qs.exclude(ref_type=StockLedger.REF_TRANSFER)

    opening_map = _as_map(
        opening_qs.values('material_id').annotate(
            qty_open=Coalesce(Sum('qty_delta'), ZERO_QTY),
            val_open=Coalesce(Sum(_signed_amount()), ZERO_AMT),
        ),
        ('qty_open', 'val_open'),
    )
    period_map = _as_map(
        period_qs.values('material_id').annotate(
            qty_in=Coalesce(Sum(_qty_in()), ZERO_QTY),
            val_in=Coalesce(Sum(_val_in()), ZERO_AMT),
            qty_out=Coalesce(Sum(_qty_out()), ZERO_QTY),
            val_out=Coalesce(Sum(_val_out()), ZERO_AMT),
        ),
        ('qty_in', 'val_in', 'qty_out', 'val_out'),
    )

    materials = Material.objects.select_related('unit', 'category')
    search = (search or '').strip()
    if search:
        materials = apply_material_search(materials, search)
    else:
        moved_ids = set(opening_map) | set(period_map)
        materials = materials.filter(Q(is_active=True) | Q(pk__in=moved_ids))
    materials = list(materials.order_by('variant_group', 'code'))

    all_rows = []
    totals = _zero_totals()
    for material in materials:
        opening = opening_map.get(material.pk, {})
        period = period_map.get(material.pk, {})
        qty_open = opening.get('qty_open') or Decimal('0')
        val_open = opening.get('val_open') or Decimal('0')
        qty_in = period.get('qty_in') or Decimal('0')
        val_in = period.get('val_in') or Decimal('0')
        qty_out = period.get('qty_out') or Decimal('0')
        val_out = period.get('val_out') or Decimal('0')
        row = {
            'material': material,
            'group_name': (material.variant_group or '').strip(),
            'code': material.code,
            'name': material.name,
            'qty_open': qty_open,
            'val_open': val_open,
            'qty_in': qty_in,
            'val_in': val_in,
            'qty_out': qty_out,
            'val_out': val_out,
            'qty_close': qty_open + qty_in - qty_out,
            'val_close': val_open + val_in - val_out,
        }
        _add_totals(totals, row)
        all_rows.append(row)

    all_groups = group_xnt_rows(all_rows)
    sku_count = len(all_rows)
    group_count = len(all_groups)
    if limit is None or limit <= 0:
        groups = all_groups
    else:
        groups = all_groups[:limit]
    return {
        'groups': groups,
        'all_rows': all_rows,
        'totals': totals,
        'total_count': group_count,
        'sku_count': sku_count,
        'displayed_count': len(groups),
        'truncated': group_count > len(groups),
        'display_limit': DISPLAY_LIMIT if limit is None else limit,
    }


def report_xuat_nhap_ton_export_rows(
    date_from: date,
    date_to: date,
    *,
    location_id: int | None = None,
    search: str = '',
) -> list[dict]:
    data = report_xuat_nhap_ton(
        date_from,
        date_to,
        location_id=location_id,
        search=search,
        limit=None,
    )
    export_rows = []
    for row in data['all_rows']:
        export_rows.append({
            label: row[key]
            for key, label in XNT_COLUMNS
        })
    totals = data['totals']
    if export_rows:
        export_rows.append({
            'Tên nhóm hàng': '',
            'Mã hàng': '',
            'Tên hàng': 'Tổng cộng',
            **{label: totals[key] for key, label in XNT_COLUMNS if key not in ('group_name', 'code', 'name')},
        })
    return export_rows
