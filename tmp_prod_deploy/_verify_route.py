import base64
import cProfile
import importlib
import io
import pstats
import time
from collections import Counter, deque

from django.conf import settings
from django.db import connection, reset_queries
from django.urls import reverse
from django.utils import timezone

from hrm import request_cache

settings.DEBUG = True
connection.queries_log = deque(maxlen=200000)
reverse('san_xuat:plan_board')
PY = __PY__


def snap_board(board):
    out = []
    for r in getattr(board, 'rows', []) or []:
        bars = []
        for name in ('bars', 'team_bars', 'stage_rows'):
            for b in getattr(r, name, None) or []:
                d = {}
                for k, v in sorted(vars(b).items()):
                    if isinstance(v, (str, int, float, bool)) or v is None or type(v).__name__ in ('Decimal', 'date'):
                        d[k] = str(v)
                    elif isinstance(v, list):
                        d[k] = str(len(v)) + ':' + ','.join(
                            str(getattr(x, 'done', '')) + '/' + str(getattr(x, 'qty', getattr(x, 'plan', ''))) for x in v
                        )
                bars.append((name, tuple(sorted(d.items()))))
        out.append((r.order.pk, tuple(bars)))
    return out


def run(label, profile=False):
    from san_xuat.services import plan_board as pb
    request_cache.begin(enabled=True)
    reset_queries()
    pr = cProfile.Profile() if profile else None
    if pr:
        pr.enable()
    t0 = time.perf_counter()
    months = pb._clamp_route_months(None)
    ws, we = pb._months_bounds(timezone.localdate(), months)
    ps, _ = pb._months_bounds(pb._shift_month(ws, -1), 1)
    rows = pb.build_plan_board_rows(include_released=True, date_from=ps, date_to=we, date_mode='range', persist_side_effects=False)
    t1 = time.perf_counter()
    board = pb.build_order_timeline(rows, range_from=None, months=months)
    board = pb.filter_route_timeline(board, team_ids=[], include_unassigned_team=False)
    stats = pb.build_route_stats(board)
    t2 = time.perf_counter()
    if pr:
        pr.disable()
    n = len(connection.queries)
    shapes = Counter(q['sql'].split(' WHERE ')[0][:110] for q in connection.queries)
    request_cache.end()
    print(f'[{label}] rows={t1 - t0:.2f}s timeline={t2 - t1:.2f}s total={t2 - t0:.2f}s queries={n}')
    for k, c in shapes.most_common(6):
        print(f'     {c:5d}  {k}')
    stage = [(r.order.pk, tuple((s.slug, str(s.done), str(s.plan)) for s in (getattr(r, 'stage_progress', None) or []))) for r in rows]
    return (snap_board(board), stage, repr(sorted(vars(stats).keys()))), pr


run('warm')
before, _ = run('BEFORE')
for modname, src in PY.items():
    mod = importlib.import_module(modname)
    exec(compile(base64.b64decode(src).decode(), mod.__file__, 'exec'), mod.__dict__)
run('AFTER-warm')
after, pr = run('AFTER', profile=True)
print('SAME_BOARD=', before[0] == after[0], 'bars=', sum(len(b) for _, b in before[0]))
print('SAME_STAGE_PROGRESS=', before[1] == after[1])
if before[0] != after[0]:
    for a, b in zip(before[0], after[0]):
        if a != b:
            print('DIFF order', a[0])
            for x, y in zip(a[1], b[1]):
                if x != y:
                    print('  before', x)
                    print('  after ', y)
                    break
            break
s = io.StringIO()
st = pstats.Stats(pr, stream=s)
st.sort_stats('cumulative').print_stats(r'/app/(san_xuat|hrm)/', 22)
st.print_callers(r'related_manager_rows|board_slug_from_work_center_id|sales_order_line_routing')
print(s.getvalue()[-9000:])
