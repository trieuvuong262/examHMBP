import base64
import importlib
import re
import time

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from django.urls import reverse

from hrm import request_cache

reverse('san_xuat:plan_board')
PY = __PY__
user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
URLS = {
    'route': '/san-xuat/ke-hoach/bang/?mode=list&tab=route',
    'queue': '/san-xuat/ke-hoach/bang/?mode=list&tab=queue',
}


def call(url):
    from san_xuat.views_hub import plan_board
    req = RequestFactory().get(url)
    req.user = user
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    request_cache.begin(enabled=True)
    t0 = time.perf_counter()
    resp = plan_board(req)
    dt = time.perf_counter() - t0
    request_cache.end()
    return resp.content.decode(), dt


def norm(html):
    html = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'CSRF', html)
    html = re.sub(r'"csrfToken"\s*:\s*"[^"]+"', 'CSRF', html)
    return re.sub(r'\s+', ' ', html).strip()


old = {}
for k, u in URLS.items():
    call(u)
    html, dt = call(u)
    old[k] = html
    print(f'OLD {k}: {dt:.2f}s {len(html)//1024} KB')

for modname, src in PY.items():
    mod = importlib.import_module(modname)
    exec(compile(base64.b64decode(src).decode(), mod.__file__, 'exec'), mod.__dict__)

for k, u in URLS.items():
    call(u)
    html, dt = call(u)
    a, b = norm(old[k]), norm(html)
    same = a == b
    print(f'NEW {k}: {dt:.2f}s {len(html)//1024} KB  IDENTICAL_HTML={same}')
    if not same:
        i = next((x for x in range(min(len(a), len(b))) if a[x] != b[x]), min(len(a), len(b)))
        print('  old:', a[max(0, i - 200):i + 200])
        print('  new:', b[max(0, i - 200):i + 200])
