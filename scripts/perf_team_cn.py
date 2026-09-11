"""Đo hiệu năng trang /reports/sx/team/ — số query, thời gian từng phase, khối lượng dữ liệu.

Chạy: python scripts/perf_team_cn.py
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

rp = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_PRODUCTION)
anchor = rp.aggregate(m=Max('report_date'))['m']

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
print('users co company-wide report access:', len(viewers))
viewer = viewers[0] if viewers else User.objects.filter(is_active=True, is_superuser=True).first()
if viewer is None:
    print('KHONG tim duoc viewer -> dung')
    raise SystemExit(1)
print('viewer = %s | team size = %d' % (viewer.username, get_team_report_members(viewer).count()))

rf = RequestFactory()

# Đếm số lần gọi các hàm nghi vấn N+1
from hrm import request_cache  # noqa: E402
from reports import production_hourly as ph  # noqa: E402

CALLS = Counter()


def _wrap(module, name):
    original = getattr(module, name)

    def wrapper(*args, **kwargs):
        CALLS[name] += 1
        return original(*args, **kwargs)

    setattr(module, name, wrapper)


for _fn in (
    '_is_subsequent_timed_session_product',
    'session_effective_hours',
    '_product_accounted_work_hours',
    'list_production_products',
    'compute_day_work_waste_summary',
):
    _wrap(ph, _fn)


def run(label: str, date_from, date_to):
    qs = f'?from={date_from.isoformat()}&to={date_to.isoformat()}'
    request = rf.get('/reports/sx/team/' + qs)
    request.user = viewer
    request.session = SessionStore()
    request._messages = FallbackStorage(request)

    CALLS.clear()
    request_cache.begin(True)  # mô phỏng RequestCacheMiddleware trên GET
    reset_queries()
    t0 = time.perf_counter()
    resp = reports_views.team_reports_cn(request)
    t_view = time.perf_counter() - t0

    queries = list(connection.queries)
    n_q = len(queries)
    t_sql = sum(float(q['time']) for q in queries)
    top = Counter(q['sql'][:100] for q in queries)

    t1 = time.perf_counter()
    if hasattr(resp, 'render'):
        resp.render()
    t_render = time.perf_counter() - t1
    n_q_render = len(connection.queries) - n_q
    content_len = len(getattr(resp, 'content', b'') or b'')
    request_cache.end()

    ctx = getattr(resp, 'context_data', None) or {}
    rows = sum(len(g.get('rows') or []) for g in (ctx.get('department_groups') or []))

    print()
    print(f'--- {label}  [{date_from} .. {date_to}]')
    print(f'    status            : {getattr(resp, "status_code", "?")}')
    print(f'    VIEW  (python+sql): {t_view:7.2f}s   queries={n_q:5d}  sql_time={t_sql:6.2f}s')
    print(f'    RENDER template   : {t_render:7.2f}s   queries={n_q_render:5d}')
    print(f'    TONG              : {t_view + t_render:7.2f}s')
    print(f'    rows render       : {rows}')
    print(f'    HTML size         : {content_len / 1024:.0f} KB')
    print('    top SQL lap nhieu nhat:')
    for sql, c in top.most_common(5):
        print(f'      {c:5d}x  {sql}')
    print('    so lan goi ham (python-level):')
    for name, c in CALLS.most_common():
        print(f'      {c:7d}x  {name}')


run('1 ngay', anchor, anchor)
run('7 ngay (mac dinh SX)', anchor - timedelta(days=6), anchor)
run('30 ngay', anchor - timedelta(days=29), anchor)

print()
print('=' * 74)
print('CPROFILE — 7 ngay (mac dinh SX)')
print('=' * 74)
import cProfile  # noqa: E402
import pstats  # noqa: E402
import io as _io  # noqa: E402

_req = rf.get('/reports/sx/team/?from=%s&to=%s' % (
    (anchor - timedelta(days=6)).isoformat(), anchor.isoformat()))
_req.user = viewer
_req.session = SessionStore()
_req._messages = FallbackStorage(_req)
request_cache.begin(True)
_pr = cProfile.Profile()
_pr.enable()
reports_views.team_reports_cn(_req)
_pr.disable()
request_cache.end()
_s = _io.StringIO()
pstats.Stats(_pr, stream=_s).sort_stats('cumulative').print_stats(28)
print('\n'.join(_s.getvalue().splitlines()[:45]))
