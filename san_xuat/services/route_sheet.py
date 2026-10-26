"""Bảng lộ trình đã tính sẵn.

Trang KHSX đọc payload. Công đoạn, thống kê và BOM chỉ chạy lại khi lịch,
tiến độ hoặc phiếu xuất đổi.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from san_xuat.hub_models import SxRouteSheet, SxSalesOrder


def mark_route_sheet_dirty(order_id: int | None) -> None:
    """Gom đơn cần tính lại, chạy một lần sau khi transaction commit."""
    oid = int(order_id or 0)
    if oid <= 0:
        return
    conn = transaction.get_connection()
    bucket = getattr(conn, '_route_sheet_dirty', None)
    if bucket is None:
        bucket = set()
        conn._route_sheet_dirty = bucket

        def _flush(ids=bucket, connection=conn):
            pending = list(ids)
            ids.clear()
            connection._route_sheet_dirty = None
            if pending:
                # Rebuilding the route payload can be expensive.  Do not make
                # the request that changed production progress wait for it;
                # otherwise the modal appears to hang after the database write.
                from PortalJustPlay.background import enqueue

                enqueue(
                    refresh_route_sheets,
                    pending,
                    timeout=900,
                    description='Refresh route sheets',
                )

        transaction.on_commit(_flush)
    bucket.add(oid)


def ensure_route_sheets(
    order_ids,
    *,
    range_from: date,
    range_to: date,
) -> None:
    """Tính những đơn chưa có bản ghi phủ khoảng ngày đang xem."""
    ids = [int(pk) for pk in (order_ids or []) if int(pk or 0) > 0]
    if not ids:
        return
    existing = {
        int(sid): (start, end)
        for sid, start, end in SxRouteSheet.objects.filter(
            sales_order_id__in=ids,
        ).values_list('sales_order_id', 'cover_from', 'cover_to')
    }
    missing = [
        pk for pk in ids
        if pk not in existing
        or existing[pk][0] > range_from
        or existing[pk][1] < range_to
    ]
    if missing:
        refresh_route_sheets(missing, range_from=range_from, range_to=range_to)


def refresh_route_sheets(
    order_ids,
    *,
    range_from: date | None = None,
    range_to: date | None = None,
) -> None:
    """Dựng lại payload lộ trình cho các đơn. Gọi sau khi dữ liệu nguồn đổi."""
    from san_xuat.services.plan_board import (
        build_order_timeline,
        build_plan_board_rows,
        route_list_status,
    )

    ids = list({int(pk) for pk in (order_ids or []) if int(pk or 0) > 0})
    if not ids:
        return
    rows = build_plan_board_rows(
        include_released=True,
        persist_side_effects=False,
        for_route=True,
        order_ids=ids,
    )
    today = timezone.localdate()
    found: set[int] = set()
    for row in rows:
        found.add(int(row.order.pk))
        cover_from, cover_to = _cover_bounds(
            row, today, range_from=range_from, range_to=range_to,
        )
        board = build_order_timeline([row], range_from=cover_from, range_to=cover_to)
        timeline = board.rows[0] if board.rows else None
        payload = json.loads(json.dumps(_dump_timeline(timeline), default=str))
        SxRouteSheet.objects.update_or_create(
            sales_order_id=row.order.pk,
            defaults={
                'plan_status': route_list_status(row.order),
                'cover_from': cover_from,
                'cover_to': cover_to,
                'khsx_overrun': bool(getattr(row, 'khsx_overrun', False)),
                'payload': payload,
            },
        )
    stale = [pk for pk in ids if pk not in found]
    if stale:
        SxRouteSheet.objects.filter(sales_order_id__in=stale).delete()


def route_sheet_deadline_ids(order_ids, deadline: str, today: date) -> set[int]:
    """Id đơn khớp Trễ hạn / Đúng hạn theo hạn giao và cờ KHSX đã lưu."""
    ids = [int(pk) for pk in (order_ids or []) if int(pk or 0) > 0]
    if not ids:
        return set()
    qs = SxRouteSheet.objects.filter(sales_order_id__in=ids)
    if deadline == 'overdue':
        qs = qs.filter(Q(khsx_overrun=True) | Q(sales_order__due_date__lt=today))
    elif deadline == 'on_time':
        qs = qs.exclude(khsx_overrun=True).filter(
            Q(sales_order__due_date__isnull=True) | Q(sales_order__due_date__gte=today),
        )
    else:
        return set(ids)
    return {int(pk) for pk in qs.values_list('sales_order_id', flat=True)}


def load_route_board(order_ids, *, range_from: date, range_to: date):
    """Đọc lưới đã tính và chiếu lên khoảng ngày đang xem."""
    from san_xuat.services.plan_board import (
        MoTimelineBoard,
        PlanTimelineRow,
        RouteStageRow,
        TeamTimelineBar,
        _bar_columns,
        _range_label,
        _stage_day_cells,
        _timeline_axis,
        route_default_bounds,
    )

    ids = [int(pk) for pk in (order_ids or []) if int(pk or 0) > 0]
    today = timezone.localdate()
    start, end = range_from, range_to
    if end < start:
        start, end = end, start
    axis_days, month_spans, span = _timeline_axis(start, end, today)
    sheets = {
        int(sheet.sales_order_id): sheet
        for sheet in SxRouteSheet.objects.filter(sales_order_id__in=ids).select_related('sales_order')
    } if ids else {}
    rows: list[PlanTimelineRow] = []
    for oid in ids:
        sheet = sheets.get(oid)
        if sheet is None:
            continue
        hydrated = _hydrate_row(
            sheet,
            axis_days=axis_days,
            range_start=start,
            range_end=end,
            today=today,
            PlanTimelineRow=PlanTimelineRow,
            RouteStageRow=RouteStageRow,
            TeamTimelineBar=TeamTimelineBar,
            stage_day_cells=_stage_day_cells,
            bar_columns=_bar_columns,
        )
        if hydrated is not None:
            rows.append(hydrated)
    span_days = (end - start).days + 1
    default_from, default_to = route_default_bounds(today)
    prev_to = start - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span_days - 1)
    next_from = end + timedelta(days=1)
    next_to = next_from + timedelta(days=span_days - 1)
    today_col = (today - start).days + 1 if start <= today <= end else None
    return MoTimelineBoard(
        range_start=start,
        range_end=end,
        days=axis_days,
        month_spans=month_spans,
        rows=rows,
        today=today,
        today_col=today_col,
        prev_from=prev_from,
        prev_to=prev_to,
        next_from=next_from,
        next_to=next_to,
        unscheduled=[],
        search='',
        month_label=_range_label(start, end),
        is_current_month=(start == default_from and end == default_to),
        months=1,
    )


def connect_route_sheet_signals() -> None:
    from django.db.models.signals import post_delete, post_save

    from san_xuat.hub_models import SxSubcontractOrder

    post_save.connect(
        _on_sales_order_saved,
        sender=SxSalesOrder,
        dispatch_uid='sx_route_sheet_order_save',
    )
    post_save.connect(
        _on_subcontract_saved,
        sender=SxSubcontractOrder,
        dispatch_uid='sx_route_sheet_gc_save',
    )
    post_delete.connect(
        _on_subcontract_saved,
        sender=SxSubcontractOrder,
        dispatch_uid='sx_route_sheet_gc_delete',
    )


def _on_sales_order_saved(sender, instance, update_fields=None, **kwargs):
    watched = {
        'plan_status', 'plan_start_date', 'due_date', 'request_date',
        'plan_priority', 'plan_color', 'npl_status', 'npl_ready_date',
        'npl_lead_days', 'npl_kit_days',
    }
    if update_fields is not None and not (set(update_fields) & watched):
        return
    if instance.is_demo or instance.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        return
    mark_route_sheet_dirty(instance.pk)


def _on_subcontract_saved(sender, instance, **kwargs):
    mark_route_sheet_dirty(getattr(instance, 'sales_order_id', None))


def _cover_bounds(row, today: date, *, range_from: date | None, range_to: date | None):
    order = row.order
    anchor = row.khsx_start or order.plan_start_date or order.request_date or today
    finish = row.khsx_end or order.due_date or anchor
    cover_from = min(anchor, today) - timedelta(days=60)
    cover_to = max(finish, today) + timedelta(days=120)
    if range_from is not None:
        cover_from = min(cover_from, range_from)
    if range_to is not None:
        cover_to = max(cover_to, range_to)
    if cover_to < cover_from:
        cover_to = cover_from
    return cover_from, cover_to


def _dump_timeline(row) -> dict:
    if row is None:
        return {'visible': False, 'stages': []}
    return {
        'visible': True,
        'start': _iso(row.start),
        'end': _iso(row.end),
        'duration_label': row.duration_label or '',
        'duration_script_id': row.duration_script_id or '',
        'duration_detail': row.duration_detail or {},
        'subtitle': row.subtitle or '',
        'can_drag': bool(row.can_drag),
        'product_images': list(row.product_images or []),
        'product_code_label': row.product_code_label or '',
        'product_name_label': row.product_name_label or '',
        'qty_label': row.qty_label or '',
        'color_label': row.color_label or '',
        'track_color': row.track_color or '',
        'track_soft': row.track_soft or '',
        'color_custom': bool(row.color_custom),
        'npl_needs': list(row.npl_needs or []),
        'npl_script_id': row.npl_script_id or '',
        'can_complete': bool(row.can_complete),
        'status_key': row.status_key or '',
        'status_label': row.status_label or '',
        'stages': [_dump_stage(stage) for stage in (row.stage_rows or [])],
    }


def _dump_stage(stage) -> dict:
    days = {}
    for cell in stage.cells or []:
        bar = getattr(cell, 'bar', None)
        if bar is None:
            continue
        key = _iso(getattr(cell, 'date', None) or bar.plan_date or bar.start)
        if not key:
            continue
        days[key] = {
            'slug': bar.slug or '',
            'label': bar.label or '',
            'start': _iso(bar.start),
            'end': _iso(bar.end),
            'plan_date': _iso(bar.plan_date),
            'can_drag': bool(bar.can_drag),
            'qty_label': bar.qty_label or '',
            'done_qty_label': bar.done_qty_label or '0',
            'is_split': bool(bar.is_split),
            'segment_id': int(bar.segment_id or 0),
            'team_qty_total': bar.team_qty_total or '',
            'done_qty_total': bar.done_qty_total or '0',
            'work_center_id': int(bar.work_center_id or 0),
            'gc_hired': bool(bar.gc_hired),
            'gc_pk': int(bar.gc_pk or 0),
            'gc_code': bar.gc_code or '',
            'gc_title': bar.gc_title or '',
        }
    return {
        'slug': stage.slug or '',
        'label': stage.label or '',
        'short_label': stage.short_label or '',
        'team_label': stage.team_label or '',
        'work_center_id': int(stage.work_center_id or 0),
        'team_qty_total': stage.team_qty_total or '',
        'total_label': stage.total_label or '',
        'done_total_label': stage.done_total_label or '0',
        'can_drag': bool(stage.can_drag),
        'can_split': bool(stage.can_split),
        'first_date': _iso(stage.first_date),
        'last_date': _iso(stage.last_date),
        'schedule_start': _iso(stage.schedule_start),
        'headcount': int(stage.headcount or 0),
        'efficiency_pct': _num(stage.efficiency_pct),
        'catalog_headcount': int(stage.catalog_headcount or 0),
        'catalog_efficiency_pct': _num(stage.catalog_efficiency_pct),
        'work_hours_per_day': _num(stage.work_hours_per_day),
        'labor_minutes': _num(stage.labor_minutes),
        'smv_seconds': _num(stage.smv_seconds),
        'qty_per_day': _num(stage.qty_per_day),
        'planned_qty': _num(stage.planned_qty),
        'gc_hired': bool(stage.gc_hired),
        'gc_pk': int(stage.gc_pk or 0),
        'gc_code': stage.gc_code or '',
        'gc_title': stage.gc_title or '',
        'progress_mo_id': int(stage.progress_mo_id or 0),
        'progress_slug': stage.progress_slug or '',
        'npl_dept': stage.npl_dept or '',
        'npl_ready': int(stage.npl_ready or 0),
        'npl_total': int(stage.npl_total or 0),
        'npl_state': stage.npl_state or '',
        'npl_title': stage.npl_title or '',
        'npl_range': stage.npl_range or '',
        'npl_status': stage.npl_status or '',
        'is_npl_prep': bool(stage.is_npl_prep),
        'days': days,
    }


def _hydrate_row(
    sheet,
    *,
    axis_days,
    range_start,
    range_end,
    today,
    PlanTimelineRow,
    RouteStageRow,
    TeamTimelineBar,
    stage_day_cells,
    bar_columns,
):
    payload = sheet.payload or {}
    if not payload.get('visible'):
        return None
    order = sheet.sales_order
    due = order.due_date
    is_late = bool(sheet.khsx_overrun or (due and due < today))
    stages = []
    for raw in payload.get('stages') or []:
        by_day = {}
        for key, bar in (raw.get('days') or {}).items():
            day = _parse_date(key)
            if day is None or day < range_start or day > range_end:
                continue
            placed = bar_columns(day, day, range_start, range_end)
            col_start = placed[0] if placed else 1
            by_day[day] = TeamTimelineBar(
                slug=bar.get('slug') or raw.get('slug') or '',
                label=bar.get('label') or raw.get('label') or '',
                start=_parse_date(bar.get('start')) or day,
                end=_parse_date(bar.get('end')) or day,
                col_start=col_start,
                col_end=col_start + 1,
                vis_days=1,
                bar_text=bar.get('qty_label') or '',
                clips_left=False,
                clips_right=False,
                can_drag=bool(bar.get('can_drag')),
                span_days=1,
                minutes=Decimal('0'),
                duration_label='',
                grid_row=0,
                placed=True,
                qty_label=bar.get('qty_label') or '',
                done_qty_label=bar.get('done_qty_label') or '0',
                is_split=bool(bar.get('is_split')),
                segment_id=int(bar.get('segment_id') or 0),
                plan_date=_parse_date(bar.get('plan_date')) or day,
                team_qty_total=bar.get('team_qty_total') or '',
                done_qty_total=bar.get('done_qty_total') or '0',
                work_center_id=int(bar.get('work_center_id') or 0),
                gc_hired=bool(bar.get('gc_hired')),
                gc_pk=int(bar.get('gc_pk') or 0),
                gc_code=bar.get('gc_code') or '',
                gc_title=bar.get('gc_title') or '',
            )
        stages.append(RouteStageRow(
            slug=raw.get('slug') or '',
            label=raw.get('label') or '',
            short_label=raw.get('short_label') or '',
            team_label=raw.get('team_label') or '',
            work_center_id=int(raw.get('work_center_id') or 0),
            team_qty_total=raw.get('team_qty_total') or '',
            total_label=raw.get('total_label') or '',
            done_total_label=raw.get('done_total_label') or '0',
            can_drag=bool(raw.get('can_drag')),
            can_split=bool(raw.get('can_split')),
            first_date=_parse_date(raw.get('first_date')),
            last_date=_parse_date(raw.get('last_date')),
            cells=stage_day_cells(axis_days, by_day),
            headcount=int(raw.get('headcount') or 0),
            efficiency_pct=_dec(raw.get('efficiency_pct')),
            catalog_headcount=int(raw.get('catalog_headcount') or 0),
            catalog_efficiency_pct=_dec(raw.get('catalog_efficiency_pct')),
            work_hours_per_day=_dec(raw.get('work_hours_per_day')),
            labor_minutes=_dec(raw.get('labor_minutes')),
            smv_seconds=_dec(raw.get('smv_seconds')),
            qty_per_day=_dec(raw.get('qty_per_day')),
            planned_qty=_dec(raw.get('planned_qty')),
            gc_hired=bool(raw.get('gc_hired')),
            gc_pk=int(raw.get('gc_pk') or 0),
            gc_code=raw.get('gc_code') or '',
            gc_title=raw.get('gc_title') or '',
            progress_mo_id=int(raw.get('progress_mo_id') or 0),
            progress_slug=raw.get('progress_slug') or '',
            is_npl_prep=bool(raw.get('is_npl_prep')),
            schedule_start=_parse_date(raw.get('schedule_start')),
            npl_state=raw.get('npl_state') or '',
            npl_title=raw.get('npl_title') or '',
            npl_range=raw.get('npl_range') or '',
            npl_status=raw.get('npl_status') or '',
            npl_dept=raw.get('npl_dept') or '',
            npl_ready=int(raw.get('npl_ready') or 0),
            npl_total=int(raw.get('npl_total') or 0),
        ))
    start = _parse_date(payload.get('start')) or range_start
    end = _parse_date(payload.get('end')) or start
    return PlanTimelineRow(
        order=order,
        start=start,
        end=end,
        col_start=1,
        col_end=2,
        vis_days=1,
        bar_text='',
        is_late=is_late,
        clips_left=start < range_start,
        clips_right=end > range_end,
        status_key=payload.get('status_key') or order.plan_status or '',
        status_label=payload.get('status_label') or '',
        duration_label=payload.get('duration_label') or '',
        duration_script_id=payload.get('duration_script_id') or '',
        subtitle=payload.get('subtitle') or '',
        duration_detail=payload.get('duration_detail') or {},
        can_drag=bool(payload.get('can_drag')),
        product_images=list(payload.get('product_images') or []),
        product_code_label=payload.get('product_code_label') or '',
        product_name_label=payload.get('product_name_label') or '',
        qty_label=payload.get('qty_label') or '',
        color_label=payload.get('color_label') or '',
        track_color=payload.get('track_color') or '#dc2626',
        track_soft=payload.get('track_soft') or '#fef2f2',
        color_custom=bool(payload.get('color_custom')),
        npl_needs=list(payload.get('npl_needs') or []),
        npl_script_id=payload.get('npl_script_id') or '',
        can_complete=bool(payload.get('can_complete')),
        stage_rows=stages,
    )


def _iso(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return ''


def _parse_date(raw) -> date | None:
    text = (raw or '').strip() if isinstance(raw, str) else ''
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _num(value) -> str:
    if value is None or value == '':
        return '0'
    return str(value)


def _dec(raw) -> Decimal:
    try:
        return Decimal(str(raw if raw not in (None, '') else '0'))
    except Exception:
        return Decimal('0')
