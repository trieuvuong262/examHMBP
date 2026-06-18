"""Quick check meal push eligibility for admin on portal."""
import re
import sys

import requests

BASE = 'https://portal.justplay.vn'
USER = 'admin'
PASS = '123123sS@@'


def main():
    s = requests.Session()
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
    })
    r = s.get(f'{BASE}/accounts/login/', timeout=30)
    print('login page', r.status_code)
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not m:
        print('no csrf')
        sys.exit(1)
    csrf = m.group(1)
    r2 = s.post(
        f'{BASE}/accounts/login/',
        data={
            'username': USER,
            'password': PASS,
            'csrfmiddlewaretoken': csrf,
            'next': '/',
        },
        headers={'Referer': f'{BASE}/accounts/login/'},
        timeout=30,
        allow_redirects=True,
    )
    print('login post', r2.status_code, r2.url)
    home = s.get(f'{BASE}/', timeout=30)
    print('home', home.status_code)
    print('js_version_20260618d', '20260618d' in home.text)
    needles = [
        'jpMealPushPrompt',
        'jpMealPushEnable',
        'JP_MEAL_PUSH',
        'jpMealPushTest',
    ]
    for n in needles:
        print(f'  {n}:', n in home.text)
    m2 = re.search(r'JP_MEAL_PUSH\s*=\s*(\{[^;]+\})', home.text)
    if m2:
        print('config:', m2.group(1)[:300])
    for path in [
        '/tien-ich/push/status/',
        '/tien-ich/push/vapid-public-key/',
    ]:
        resp = s.get(f'{BASE}{path}', timeout=30)
        print(path, resp.status_code, resp.text[:250])

    # CSRF for POST
    home2 = s.get(f'{BASE}/', timeout=30)
    mcsrf = re.search(r'name="csrf-token" content="([^"]+)"', home2.text)
    if not mcsrf:
        mcsrf = re.search(r'csrf-token.*?content="([^"]+)"', home2.text)
    csrf_token = mcsrf.group(1) if mcsrf else ''
    print('csrf meta', bool(csrf_token))
    test_resp = s.post(
        f'{BASE}/tien-ich/push/test/',
        headers={
            'X-CSRFToken': csrf_token,
            'Content-Type': 'application/json',
            'Referer': f'{BASE}/',
        },
        json={},
        timeout=30,
    )
    print('push test', test_resp.status_code, test_resp.text[:400])


if __name__ == '__main__':
    main()
