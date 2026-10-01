"""Thời gian phản hồi request / truy vấn DB theo ngày và theo tháng (tab Phản hồi)."""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TARGET_P95_MS = 1000
TARGET_LE_1S_PCT = 95.0
SLOW_QUERY_MS = 500


def _local_today() -> date:
    return timezone.localdate()


def aggregate_response_days() -> int:
    """Tổng hợp các ngày còn đủ dữ liệu trong nhật ký thao tác vào ResponseTimeDaily.

    Ngày cũ nhất trong nhật ký đã bị xóa một phần (giữ 7 ngày) nên bỏ qua,
    không ghi đè số đã tổng hợp trước đó.
    """
    from audit.models import ResponseTimeDaily
    from audit.retention import ACTIVITY_LOG_RETENTION_DAYS

    tz = settings.TIME_ZONE
    first_day = timezone.localdate(timezone.now() - timedelta(days=ACTIVITY_LOG_RETENTION_DAYS)) + timedelta(days=1)
    start = timezone.make_aware(datetime.combine(first_day, time.min))

    with connection.cursor() as c:
        c.execute(
            """
            SELECT (created_at AT TIME ZONE %s)::date AS d,
                   count(*),
                   coalesce(sum(duration_ms), 0),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
                   max(duration_ms),
                   count(*) FILTER (WHERE duration_ms <= 1000),
                   count(*) FILTER (WHERE duration_ms > 3000)
            FROM audit_useractivitylog
            WHERE duration_ms IS NOT NULL AND created_at >= %s
            GROUP BY 1
            """,
            [tz, start],
        )
        day_rows = c.fetchall()
        c.execute(
            """
            SELECT (created_at AT TIME ZONE %s)::date AS d,
                   coalesce(nullif(url_name, ''), '(khác)'),
                   count(*),
                   coalesce(sum(duration_ms), 0),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
                   max(duration_ms)
            FROM audit_useractivitylog
            WHERE duration_ms IS NOT NULL AND created_at >= %s
            GROUP BY 1, 2
            """,
            [tz, start],
        )
        url_rows = c.fetchall()

    by_day: dict[date, list[dict]] = {}
    for d, url_name, n, total, p95, mx in url_rows:
        by_day.setdefault(d, []).append({
            'url_name': url_name,
            'n': int(n),
            'total_ms': int(total),
            'p95_ms': int(round(p95 or 0)),
            'max_ms': int(mx or 0),
        })

    saved = 0
    for d, n, total, p50, p95, mx, le1, gt3 in day_rows:
        defaults = {
            'request_count': int(n),
            'total_ms': int(total),
            'p50_ms': int(round(p50 or 0)),
            'p95_ms': int(round(p95 or 0)),
            'max_ms': int(mx or 0),
            'le_1s_count': int(le1),
            'gt_3s_count': int(gt3),
            'by_url': by_day.get(d, []),
        }
        try:
            with transaction.atomic():
                ResponseTimeDaily.objects.update_or_create(day=d, defaults=defaults)
            saved += 1
        except IntegrityError:
            continue
    return saved


def _pg_stat_totals() -> tuple[int, float, int] | None:
    try:
        with connection.cursor() as c:
            c.execute(
                """
                SELECT coalesce(sum(calls), 0), coalesce(sum(total_exec_time), 0),
                       count(*) FILTER (WHERE mean_exec_time > %s)
                FROM pg_stat_statements
                """,
                [SLOW_QUERY_MS],
            )
            calls, total, slow = c.fetchone()
        return int(calls), float(total), int(slow)
    except Exception:
        logger.debug('pg_stat_statements unavailable', exc_info=True)
        return None


def snapshot_db_stats() -> bool:
    """Ghi (đè) ảnh chụp cộng dồn pg_stat_statements của hôm nay."""
    from audit.models import DbQuerySnapshot

    totals = _pg_stat_totals()
    if totals is None:
        return False
    calls, total, slow = totals
    try:
        with transaction.atomic():
            DbQuerySnapshot.objects.update_or_create(
                day=_local_today(),
                defaults={'calls': calls, 'total_exec_ms': total, 'slow_query_count': slow},
            )
    except IntegrityError:
        return False
    return True


def refresh_response_stats() -> None:
    try:
        aggregate_response_days()
    except Exception:
        logger.exception('aggregate_response_days failed')
    try:
        snapshot_db_stats()
    except Exception:
        logger.exception('snapshot_db_stats failed')


def parse_month(raw: str | None) -> tuple[int, int]:
    today = _local_today()
    try:
        y, m = (int(x) for x in (raw or '').split('-', 1))
        if 2000 <= y <= 2100 and 1 <= m <= 12:
            return y, m
    except (TypeError, ValueError):
        pass
    return today.year, today.month


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 2) if whole else None


def monthly_response_report(year: int, month: int) -> dict:
    from audit.models import DbQuerySnapshot, ResponseTimeDaily

    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    days = list(ResponseTimeDaily.objects.filter(day__range=(first, last)).order_by('day'))
    total_n = sum(d.request_count for d in days)
    total_ms = sum(d.total_ms for d in days)
    le1 = sum(d.le_1s_count for d in days)
    gt3 = sum(d.gt_3s_count for d in days)
    p95_weighted = (
        round(sum(d.p95_ms * d.request_count for d in days) / total_n) if total_n else None
    )
    max_p95 = max((d.p95_ms for d in days), default=None)

    url_agg: dict[str, dict] = {}
    for d in days:
        for row in d.by_url or []:
            agg = url_agg.setdefault(row['url_name'], {
                'url_name': row['url_name'], 'n': 0, 'total_ms': 0, 'p95_sum': 0, 'max_ms': 0,
            })
            agg['n'] += row['n']
            agg['total_ms'] += row['total_ms']
            agg['p95_sum'] += row['p95_ms'] * row['n']
            agg['max_ms'] = max(agg['max_ms'], row['max_ms'])
    slow_urls = []
    for agg in url_agg.values():
        if agg['n'] < 10:
            continue
        slow_urls.append({
            'url_name': agg['url_name'],
            'n': agg['n'],
            'avg_ms': round(agg['total_ms'] / agg['n']),
            'p95_ms': round(agg['p95_sum'] / agg['n']),
            'max_ms': agg['max_ms'],
        })
    slow_urls.sort(key=lambda r: r['p95_ms'], reverse=True)

    p95_scale = max((d.p95_ms for d in days), default=0) or 1
    day_rows = [{
        'day': d.day,
        'n': d.request_count,
        'avg_ms': round(d.total_ms / d.request_count) if d.request_count else 0,
        'p50_ms': d.p50_ms,
        'p95_ms': d.p95_ms,
        'max_ms': d.max_ms,
        'le_1s_pct': _pct(d.le_1s_count, d.request_count),
        'gt_3s_pct': _pct(d.gt_3s_count, d.request_count),
        'bar_pct': round(100 * d.p95_ms / p95_scale),
        'p95_ok': d.p95_ms <= TARGET_P95_MS,
    } for d in days]

    # DB: hiệu giữa các ảnh chụp liên tiếp; lấy thêm ảnh chụp cuối tháng trước làm mốc.
    snaps = list(DbQuerySnapshot.objects.filter(day__range=(first, last)).order_by('day'))
    baseline = DbQuerySnapshot.objects.filter(day__lt=first).order_by('-day').first()
    db_days = []
    db_calls = 0
    db_ms = 0.0
    prev = baseline
    for s in snaps:
        if prev is not None and s.calls >= prev.calls:
            calls, ms = s.calls - prev.calls, s.total_exec_ms - prev.total_exec_ms
        elif prev is not None:
            calls, ms = s.calls, s.total_exec_ms  # pg_stat_statements đã bị reset
        else:
            calls, ms = None, None  # ảnh chụp đầu tiên — chưa có mốc so sánh
        if calls:
            db_calls += calls
            db_ms += ms
        db_days.append({
            'day': s.day,
            'calls': calls,
            'avg_ms': round(ms / calls, 3) if calls else None,
            'slow_query_count': s.slow_query_count,
        })
        prev = s
    db_by_day = {r['day']: r for r in db_days}
    for row in day_rows:
        row['db'] = db_by_day.get(row['day'])

    prev_month = (first - timedelta(days=1)).strftime('%Y-%m')
    next_first = last + timedelta(days=1)
    next_month = next_first.strftime('%Y-%m') if next_first <= _local_today() else None

    return {
        'year': year,
        'month': month,
        'month_value': first.strftime('%Y-%m'),
        'prev_month': prev_month,
        'next_month': next_month,
        'day_count': len(days),
        'days_in_month': last.day,
        'request_count': total_n,
        'avg_ms': round(total_ms / total_n) if total_n else None,
        'p95_weighted_ms': p95_weighted,
        'max_daily_p95_ms': max_p95,
        'le_1s_pct': _pct(le1, total_n),
        'gt_3s_pct': _pct(gt3, total_n),
        'p95_ok': p95_weighted is not None and p95_weighted <= TARGET_P95_MS,
        'le_1s_ok': total_n > 0 and _pct(le1, total_n) >= TARGET_LE_1S_PCT,
        'days': day_rows,
        'slow_urls': slow_urls[:15],
        'db_calls': db_calls,
        'db_avg_ms': round(db_ms / db_calls, 3) if db_calls else None,
        'db_slow_query_count': snaps[-1].slow_query_count if snaps else None,
        'db_has_data': bool(db_calls),
        'target_p95_ms': TARGET_P95_MS,
        'target_le_1s_pct': TARGET_LE_1S_PCT,
        'slow_query_ms': SLOW_QUERY_MS,
    }


def top_slow_queries(limit: int = 10) -> list[dict]:
    """Truy vấn có thời gian trung bình cao nhất (cộng dồn từ lần reset gần nhất)."""
    try:
        with connection.cursor() as c:
            c.execute(
                """
                SELECT left(regexp_replace(query, '\\s+', ' ', 'g'), 220),
                       calls, mean_exec_time, max_exec_time, total_exec_time
                FROM pg_stat_statements
                WHERE calls >= 5
                  AND query NOT ILIKE '%%pg_stat_statements%%'
                ORDER BY mean_exec_time DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = c.fetchall()
    except Exception:
        return []
    return [{
        'query': q,
        'calls': int(calls),
        'mean_ms': round(mean, 2),
        'max_ms': round(mx, 1),
        'total_s': round(total / 1000, 1),
    } for q, calls, mean, mx, total in rows]
