import cProfile
import io
import pstats
import re
import time
from collections import Counter, deque

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection, reset_queries
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from hrm import request_cache

settings.DEBUG = True
connection.queries_log = deque(maxlen=200000)
reverse('san_xuat:plan_board')

from san_xuat.list_filters import parse_sx_date
from san_xuat.services import plan_board as pb

user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()


def step(label, fn):
    reset_queries()
    t0 = time.perf_counter()
    out = fn()
    print(f'  {label:<28} {time.perf_counter() - t0:6.2f}s  q={len(connection.queries)}')
    return out


for attempt in ('warm', 'measure'):
    print(f'[{attempt}]')
    request_cache.begin(enabled=True)
    route_months = pb._clamp_route_months(None)
    win_start, win_end = pb._months_bounds(timezone.localdate(), route_months)
    pad_start, _ = pb._months_bounds(pb._shift_month(win_start, -1), 1)
    rows = step('build_plan_board_rows', lambda: pb.build_plan_board_rows(
        include_released=True, date_from=pad_start, date_to=win_end,
        date_mode='range', persist_side_effects=False,
    ))
    board = step('build_order_timeline', lambda: pb.build_order_timeline(rows, range_from=None, months=route_months))
    step('route_team_filter_choices', lambda: pb.route_team_filter_choices(board))
    board = step('filter_route_timeline', lambda: pb.filter_route_timeline(board, team_ids=[], include_unassigned_team=False))
    step('build_route_stats', lambda: pb.build_route_stats(board))
    request_cache.end()
print(f'ROWS={len(rows)} TIMELINE_ROWS={len(getattr(board, "rows", []) or [])} months={route_months}')

from san_xuat.views_hub import plan_board


def call():
    req = RequestFactory().get('/san-xuat/ke-hoach/bang/?mode=list&tab=route')
    req.user = user
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    request_cache.begin(enabled=True)
    reset_queries()
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    resp = plan_board(req)
    pr.disable()
    dt = time.perf_counter() - t0
    n = len(connection.queries)
    shapes = Counter(q['sql'].split(' WHERE ')[0][:110] for q in connection.queries)
    request_cache.end()
    return resp, dt, n, shapes, pr


resp, dt, n, shapes, pr = call()
html = resp.content.decode()
print(f'FULL_VIEW={dt:.2f}s QUERIES={n} HTML_KB={len(html)//1024}')
for key, c in shapes.most_common(10):
    print(f'   {c:5d}  {key}')

s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(r'/app/(san_xuat|hrm)/', 35)
print(s.getvalue()[-7500:])

style_kb = sum(len(m) for m in re.findall(r'<style.*?</style>', html, re.S)) // 1024
script_kb = sum(len(m) for m in re.findall(r'<script(?![^>]*application/json).*?</script>', html, re.S)) // 1024
json_kb = sum(len(m) for m in re.findall(r'<script[^>]*application/json.*?</script>', html, re.S)) // 1024
i = html.find('id="lo-trinh"')
print(f'INLINE_STYLE_KB={style_kb} INLINE_SCRIPT_KB={script_kb} JSON_SCRIPT_KB={json_kb} LO_TRINH_START_KB={i//1024}')
for pat in ('jp-sheet-cell', 'jp-tl-slot', 'jp-tl-bar', 'jp-sheet-qty', '<tr', '<td', 'csrfmiddlewaretoken', '<form'):
    print(f'   count {pat!r}: {html.count(pat)}')
