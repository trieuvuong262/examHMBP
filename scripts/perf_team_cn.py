"""Đo hiệu năng trang /reports/sx/team/ — thời gian, số query, kích thước HTML.

Chạy: python scripts/perf_team_cn.py
Tuỳ chọn: python scripts/perf_team_cn.py --profile   (in cProfile cho khoảng 7 ngày)
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from django.db import connection, reset_queries  # noqa: E402
from django.db.models import Max  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from hrm import request_cache  # noqa: E402
from hrm.permissions import (  # noqa: E402
    get_team_report_members,
    has_company_wide_report_access,
)
from reports import views as reports_views  # noqa: E402
from reports.models import (  # noqa: E402
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION  # noqa: E402

connection.force_debug_cursor = True
User = get_user_model()
WANT_PROFILE = '--profile' in sys.argv

rp = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_PRODUCTION)
anchor = rp.aggregate(m=Max('report_date'))['m']
if anchor is None:
    print('Chua co bao cao SX nao trong DB -> dung')
    raise SystemExit(1)

print('=' * 74)
print('KHOI LUONG DU LIEU  (anchor = ngay co BC SX moi nhat: %s)' % anchor)
print('=' * 74)
print('users active            :', User.objects.filter(is_active=True).count())
print('users phong SX          :', User.objects.filter(
    is_active=True,
    profile__is_employed=True,
    profile__department__report_profile=REPORT_PROFILE_PRODUCTION,
).count())
print('DailyWorkReport total   :', DailyWorkReport.objects.count())
print('  SX                    :', rp.count())
for span in (1, 7, 30):
    lo = anchor - timedelta(days=span - 1)
    print(f'  SX {span:>2} ngay den anchor  :',
          rp.filter(report_date__gte=lo, report_date__lte=anchor).count())
print('ProductionShiftProduct  :', ProductionShiftProduct.objects.count())
print('ProductionHourlyQty     :', ProductionHourlyQuantity.objects.count())

viewers = [u for u in User.objects.filter(is_active=True).select_related('profile')
           if has_company_wide_report_access(u)]
viewer = viewers[0] if viewers else User.objects.filter(
    is_active=True, is_superuser=True,
).first()
if viewer is None:
    print('KHONG tim duoc viewer co quyen xem toan cong ty -> dung')
    raise SystemExit(1)
print('viewer = %s | team size = %d' % (
    viewer.username, get_team_report_members(viewer).count(),
))

rf = RequestFactory()


def build_request(date_from, date_to):
    request = rf.get('/reports/sx/team/?from=%s&to=%s' % (
        date_from.isoformat(), date_to.isoformat(),
    ))
    request.user = viewer
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


def run(label: str, date_from, date_to):
    request = build_request(date_from, date_to)
    request_cache.begin(True)  # mô phỏng RequestCacheMiddleware trên GET
    reset_queries()
    t0 = time.perf_counter()
    resp = reports_views.team_reports_cn(request)
    elapsed = time.perf_counter() - t0
    queries = list(connection.queries)
    request_cache.end()

    sql_time = sum(float(q['time']) for q in queries)
    content_len = len(getattr(resp, 'content', b'') or b'')
    rows = getattr(resp, 'content', b'').count(b'<tr')

    print()
    print(f'--- {label}  [{date_from} .. {date_to}]')
    print(f'    status      : {getattr(resp, "status_code", "?")}')
    print(f'    thoi gian   : {elapsed:6.2f}s   (SQL {sql_time:.2f}s)')
    print(f'    so query    : {len(queries)}')
    print(f'    HTML        : {content_len / 1024:.0f} KB   (~{rows} <tr>)')
    top = Counter(q['sql'][:100] for q in queries)
    repeated = [(sql, c) for sql, c in top.most_common(3) if c > 5]
    if repeated:
        print('    query lap nhieu (nghi van N+1):')
        for sql, c in repeated:
            print(f'      {c:5d}x  {sql}')


run('1 ngay', anchor, anchor)
run('7 ngay (mac dinh SX)', anchor - timedelta(days=6), anchor)
run('30 ngay', anchor - timedelta(days=29), anchor)

if WANT_PROFILE:
    import cProfile
    import io
    import pstats

    print()
    print('=' * 74)
    print('CPROFILE — 7 ngay')
    print('=' * 74)
    request = build_request(anchor - timedelta(days=6), anchor)
    request_cache.begin(True)
    profiler = cProfile.Profile()
    profiler.enable()
    reports_views.team_reports_cn(request)
    profiler.disable()
    request_cache.end()
    buf = io.StringIO()
    pstats.Stats(profiler, stream=buf).sort_stats('cumulative').print_stats(25)
    print('\n'.join(buf.getvalue().splitlines()[:40]))
