"""Bộ lọc chung cho danh sách hub Sản xuất (mã, tên, từ ngày–đến ngày)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from django.db.models import Q, QuerySet
from django.db.models.fields import DateField, DateTimeField
from django.http import HttpRequest
from django.utils import timezone

from utilities.date_range_filter import (
    DATE_RANGE_DEFAULT_SPAN_DAYS,
    DATE_RANGE_SPAN_CHOICES,
    date_range_span_context,
    match_date_range_span,
    parse_date_range_span_from_request,
)

LIST_DATE_RANGE_DAYS = DATE_RANGE_DEFAULT_SPAN_DAYS


def default_list_date_range(*, days: int | None = None) -> tuple[date, date]:
    """Khoảng ngày mặc định trên list (gồm hôm nay)."""
    if days is None:
        try:
            from san_xuat.services.sx_settings import sx_int

            days = sx_int(
                "list_default_date_range_days",
                LIST_DATE_RANGE_DAYS,
                min_v=1,
                max_v=90,
            )
        except Exception:
            days = LIST_DATE_RANGE_DAYS
    today = timezone.localdate()
    span = max(1, int(days))
    return today - timedelta(days=span - 1), today


@dataclass(frozen=True)
class SxFilterSpec:
    code_fields: tuple[str, ...] = ('code',)
    name_fields: tuple[str, ...] = ('name',)
    date_field: str | None = None
    date_range_fields: tuple[str, str] | None = None


@dataclass
class SxListFilters:
    code: str = ''
    name: str = ''
    date_from: date | None = None
    date_to: date | None = None
    dates_defaulted: bool = False

    @property
    def has_filters(self) -> bool:
        if self.code or self.name:
            return True
        if self.dates_defaulted:
            return False
        return bool(self.date_from or self.date_to)


def parse_sx_date(raw: str) -> date | None:
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _coalesce_list_date_range(
    parsed_from: date | None,
    parsed_to: date | None,
    *,
    span_days: int,
) -> tuple[date, date, bool]:
    """Điền ngày thiếu; dates_defaulted=True khi cả hai đầu vào đều rỗng."""
    default_from, default_to = default_list_date_range(days=span_days)
    if not parsed_from and not parsed_to:
        return default_from, default_to, True

    date_to = parsed_to or default_to
    date_from = parsed_from or (date_to - timedelta(days=max(span_days - 1, 0)))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to, False


def parse_sx_list_filters(request: HttpRequest) -> SxListFilters:
    code = (request.GET.get('code') or '').strip()
    name = (request.GET.get('name') or '').strip()
    span_days = parse_date_range_span_from_request(request, default=LIST_DATE_RANGE_DAYS)

    if 'date_from' in request.GET or 'date_to' in request.GET or 'span' in request.GET:
        raw_from = (request.GET.get('date_from') or '').strip()
        raw_to = (request.GET.get('date_to') or '').strip()
        date_from, date_to, dates_defaulted = _coalesce_list_date_range(
            parse_sx_date(raw_from),
            parse_sx_date(raw_to),
            span_days=span_days,
        )
        return SxListFilters(
            code=code,
            name=name,
            date_from=date_from,
            date_to=date_to,
            dates_defaulted=dates_defaulted and 'date_from' not in request.GET and 'date_to' not in request.GET,
        )

    date_from, date_to = default_list_date_range(days=span_days)
    return SxListFilters(
        code=code,
        name=name,
        date_from=date_from,
        date_to=date_to,
        dates_defaulted=True,
    )


def _date_filter_lookups(qs: QuerySet, field_path: str) -> tuple[str, str]:
    """Trả về suffix lookup gte/lte theo kiểu field (Date vs DateTime)."""
    parts = field_path.split('__')
    model = qs.model
    field = None
    for i, part in enumerate(parts):
        try:
            field = model._meta.get_field(part)
        except Exception:
            field = None
            break
        if field.is_relation and i < len(parts) - 1:
            model = field.related_model
            continue
        break
    if isinstance(field, DateTimeField):
        return f'{field_path}__date__gte', f'{field_path}__date__lte'
    if isinstance(field, DateField):
        return f'{field_path}__gte', f'{field_path}__lte'
    # FK path lạ hoặc không resolve được — ưu tiên DateTime (created_at/updated_at).
    return f'{field_path}__date__gte', f'{field_path}__date__lte'


def apply_sx_list_filters(qs: QuerySet, filters: SxListFilters, spec: SxFilterSpec) -> QuerySet:
    if filters.code:
        q = Q()
        for field in spec.code_fields:
            q |= Q(**{f'{field}__icontains': filters.code})
        qs = qs.filter(q)

    if filters.name:
        q = Q()
        for field in spec.name_fields:
            q |= Q(**{f'{field}__icontains': filters.name})
        qs = qs.filter(q)

    if filters.date_from or filters.date_to:
        if spec.date_range_fields:
            from_field, to_field = spec.date_range_fields
            if filters.date_from:
                qs = qs.filter(**{f'{to_field}__gte': filters.date_from})
            if filters.date_to:
                qs = qs.filter(**{f'{from_field}__lte': filters.date_to})
        elif spec.date_field:
            gte_key, lte_key = _date_filter_lookups(qs, spec.date_field)
            if filters.date_from:
                qs = qs.filter(**{gte_key: filters.date_from})
            if filters.date_to:
                qs = qs.filter(**{lte_key: filters.date_to})
    return qs


def sx_filter_context(filters: SxListFilters, *, preserve: dict[str, str] | None = None) -> dict[str, Any]:
    preserve = preserve or {}
    span_ctx = date_range_span_context(filters.date_from, filters.date_to)
    return {
        'filter_code': filters.code,
        'filter_name': filters.name,
        'filter_date_from': filters.date_from.isoformat() if filters.date_from else '',
        'filter_date_to': filters.date_to.isoformat() if filters.date_to else '',
        'has_list_filters': filters.has_filters,
        'list_filter_preserve': preserve,
        **span_ctx,
    }


def resolve_sx_period(
    request: HttpRequest,
    *,
    honor_month: bool = True,
) -> tuple[date, date, SxListFilters]:
    """Khoảng ngày thống nhất cho list + báo cáo SX (parse_sx_list_filters + chọn tháng)."""
    from calendar import monthrange

    filters = parse_sx_list_filters(request)
    month = (request.GET.get('month') or '').strip()
    raw_from = (request.GET.get('date_from') or '').strip()
    raw_to = (request.GET.get('date_to') or '').strip()

    if honor_month and month and not raw_from and not raw_to:
        try:
            y, m = month.split('-', 1)
            year, mon = int(y), int(m)
            last = monthrange(year, mon)[1]
            date_from, date_to = date(year, mon, 1), date(year, mon, last)
        except (ValueError, IndexError):
            date_from, date_to = filters.date_from, filters.date_to
        else:
            filters = SxListFilters(
                code=filters.code,
                name=filters.name,
                date_from=date_from,
                date_to=date_to,
                dates_defaulted=False,
            )
            return date_from, date_to, filters

    return filters.date_from, filters.date_to, filters


def _tuple_row_date(row: tuple, *, date_index: int | None, date_attr: str) -> date | None:
    if date_index is None or len(row) <= date_index:
        return None
    val = getattr(row[date_index], date_attr, None)
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, 'date'):
        try:
            return val.date()
        except Exception:
            return None
    return None


def prepare_hub_list(
    request: HttpRequest,
    qs: QuerySet,
    spec: SxFilterSpec,
    *,
    list_key: str | None = None,
    limit: int = 200,
    preserve: dict[str, str] | None = None,
) -> tuple[QuerySet, dict[str, Any]]:
    filters = parse_sx_list_filters(request)
    if hasattr(qs.model, 'created_by_id'):
        qs = qs.select_related('created_by')
    filtered = apply_sx_list_filters(qs, filters, spec)
    if list_key:
        from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

        filtered = apply_sx_list_sort(filtered, request, list_key)
    filtered = filtered[:limit]
    ctx = sx_filter_context(filters, preserve=preserve)
    if list_key:
        ctx.update(sx_list_grid_context(request, list_key))
    return filtered, ctx


def filter_tuple_rows(
    rows: Iterable[tuple],
    filters: SxListFilters,
    *,
    code_index: int = 0,
    name_index: int | None = None,
    code_attr: str = 'product_code',
    name_attr: str = 'product_name',
    date_index: int | None = None,
    date_attr: str = 'updated_at',
) -> list[tuple]:
    """Lọc danh sách tuple (doc, bom, …) theo mã/tên/ngày trên phần tử tương ứng."""
    out: list[tuple] = []
    for row in rows:
        head = row[code_index]
        code_val = (getattr(head, code_attr, '') or '').lower()
        name_val = (getattr(head, name_attr, '') or '').lower() if name_index is not None else ''
        if name_index is not None and len(row) > name_index:
            alt = row[name_index]
            if hasattr(alt, name_attr):
                name_val = (getattr(alt, name_attr, '') or '').lower()
        if filters.code and filters.code.lower() not in code_val:
            continue
        if filters.name and filters.name.lower() not in name_val:
            continue
        if filters.date_from or filters.date_to:
            row_date = _tuple_row_date(row, date_index=date_index, date_attr=date_attr)
            if row_date is not None:
                if filters.date_from and row_date < filters.date_from:
                    continue
                if filters.date_to and row_date > filters.date_to:
                    continue
        out.append(row)
    return out


# --- Preset theo từng màn danh sách ---

SX_FILTER_PLAN_PERIOD = SxFilterSpec(date_range_fields=('date_from', 'date_to'))
SX_FILTER_PLAN_NPL = SxFilterSpec(date_field='created_at')
SX_FILTER_NPL_PR = SxFilterSpec(name_fields=('notes',), date_field='request_date')
SX_FILTER_PURCHASE_ORDER = SxFilterSpec(name_fields=('supplier_name',), date_field='created_at')

SX_FILTER_COST_SHEET = SxFilterSpec(date_range_fields=('date_from', 'date_to'))
SX_FILTER_COST_ORDER = SxFilterSpec(
    code_fields=('code', 'kv_order_code'),
    date_range_fields=('date_from', 'date_to'),
)
SX_FILTER_COST_TYPE = SxFilterSpec(date_field='created_at')

SX_FILTER_MO = SxFilterSpec(
    code_fields=('code', 'product_code'),
    name_fields=('product_name', 'team_label'),
    date_field='order_date',
)
SX_FILTER_DISASSEMBLY = SxFilterSpec(
    code_fields=('code', 'product_code'),
    name_fields=('product_name',),
    date_field='order_date',
)
SX_FILTER_MATERIAL_ISSUE = SxFilterSpec(
    code_fields=('code', 'production_order__code', 'production_order__product_code'),
    name_fields=('production_order__product_name',),
    date_field='request_date',
)
SX_FILTER_PROD_STAT = SxFilterSpec(
    code_fields=('code', 'production_order__code', 'production_order__product_code'),
    name_fields=('production_order__product_name', 'process_name', 'team_label'),
    date_field='stat_date',
)
SX_FILTER_FG_RECEIPT = SxFilterSpec(
    code_fields=('code', 'production_order__code'),
    name_fields=('production_order__product_name',),
    date_field='request_date',
)
SX_FILTER_NPL_SURPLUS = SxFilterSpec(
    code_fields=('code', 'material_code'),
    name_fields=('material_name',),
    date_field='recorded_at',
)
SX_FILTER_WIP_HANDOVER = SxFilterSpec(
    code_fields=('code', 'production_order__code'),
    name_fields=('production_order__product_name', 'from_process', 'to_process'),
    date_field='handover_date',
)
SX_FILTER_WIP_RETURN = SxFilterSpec(
    code_fields=('code', 'handover__code'),
    name_fields=('from_process', 'to_process'),
    date_field='return_date',
)

SX_FILTER_QC_REQUEST = SxFilterSpec(
    code_fields=('code', 'product_code'),
    name_fields=('product_name', 'stage_name'),
    date_field='request_date',
)
SX_FILTER_QC_SHEET = SxFilterSpec(
    code_fields=('code', 'qc_request__code'),
    name_fields=('qc_request__product_name',),
    date_field='inspected_at',
)
SX_FILTER_QC_ALERT = SxFilterSpec(
    code_fields=('code', 'production_order__code', 'production_order__product_code'),
    name_fields=(
        'production_order__product_name',
        'production_order__team_label',
        'message',
        'process_name',
    ),
    date_field='created_at',
)
SX_FILTER_QC_CATALOG = SxFilterSpec()

SX_FILTER_WORK_ASSIGN = SxFilterSpec(
    code_fields=('code', 'production_order__code'),
    name_fields=('title', 'process_name', 'assignee_label'),
    date_field='due_date',
)
SX_FILTER_PACKING = SxFilterSpec(
    code_fields=('code', 'lot_code', 'production_order__product_code'),
    name_fields=('production_order__product_name',),
    date_field='pack_date',
)
SX_FILTER_SUBCONTRACT = SxFilterSpec(
    code_fields=('code', 'product_code'),
    name_fields=('vendor_name', 'product_name', 'process_name'),
    date_field='order_date',
)
SX_FILTER_WORK_CENTER = SxFilterSpec(name_fields=('name', 'team_label'), date_field='created_at')

SX_FILTER_TECH_DOC = SxFilterSpec(
    code_fields=('product_code',),
    name_fields=('product_name', 'notes'),
    # Không lọc theo ngày — danh sách hồ sơ luôn hiện đầy đủ
)
SX_FILTER_BOM = SxFilterSpec(
    code_fields=('tech_doc__product_code', 'version_label'),
    name_fields=('tech_doc__product_name', 'notes'),
    date_field='updated_at',
)
SX_FILTER_NCR = SxFilterSpec(
    name_fields=('process_name', 'production_order__product_name', 'notes'),
    date_field='created_at',
)
SX_FILTER_ACTUAL_COST = SxFilterSpec(
    code_fields=('code', 'production_order__code'),
    name_fields=('production_order__product_name',),
    date_field='created_at',
)
SX_FILTER_DOWNTIME = SxFilterSpec(
    name_fields=('reason', 'team_label'),
    date_field='event_date',
)
SX_FILTER_TEAM_HR = SxFilterSpec(
    code_fields=('employee_code',),
    name_fields=('employee_name', 'team_label'),
    date_field='created_at',
)

SX_FILTER_CATALOG_ITEM = SxFilterSpec(code_fields=('code',), name_fields=('name',))
SX_FILTER_CATALOG_MATERIAL = SxFilterSpec(
    code_fields=('code',),
    name_fields=('name',),
    date_field='updated_at',
)
