#!/usr/bin/env python3
"""Test báo cáo sản xuất — login + flow cơ bản trên portal."""
import re
import sys
from urllib.parse import urljoin

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else 'https://portal.justplay.vn'


def session_for(user, password):
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
    r = s.get(f'{BASE}/accounts/login/', timeout=30)
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError(f'No CSRF for {user}')
    s.post(
        f'{BASE}/accounts/login/',
        data={
            'csrfmiddlewaretoken': m.group(1),
            'username': user,
            'password': password,
            'next': '/reports/today/',
        },
        headers={'Referer': f'{BASE}/accounts/login/'},
        allow_redirects=True,
        timeout=30,
    )
    if 'login' in s.get(f'{BASE}/reports/today/', timeout=30).url.lower():
        raise RuntimeError(f'Login failed for {user}')
    return s


def csrf_from_html(html):
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    return m.group(1) if m else ''


def test_nv():
    print('=== nv.tb production report ===')
    s = session_for('nv.tb', '123123sS@')
    r = s.get(f'{BASE}/reports/today/', timeout=30)
    html = r.text
    ok = {
        'production_ui': 'jp-prod-mobile-page' in html,
        'no_auto_hourly': 'data-auto-hourly="1"' not in html,
        'hourly_modal': 'id="hourlyModal"' in html,
        'js_v20260617d': 'reports-production-hourly.js?v=20260617d' in html,
        'mount_modals_js': 'mountModalsToBody' in requests.get(
            f'{BASE}/static/js/reports-production-hourly.js?v=20260617d', timeout=30
        ).text,
    }
    for k, v in ok.items():
        print(f'  {k}: {"OK" if v else "FAIL"}')

    csrf = csrf_from_html(html)
    slot_m = re.search(r'data-slot-index="(\d+)"', html)
    if csrf and slot_m:
        r2 = s.post(
            f'{BASE}/reports/today/',
            data={
                'csrfmiddlewaretoken': csrf,
                'action': 'save_hourly',
                'slot_index': slot_m.group(1),
                'quantity': '99',
            },
            headers={'Referer': f'{BASE}/reports/today/'},
            allow_redirects=True,
            timeout=30,
        )
        print(f'  save_hourly POST: {r2.status_code} -> {r2.url}')
        print(f'  after_save_no_auto_hourly: {"OK" if "data-auto-hourly=\"1\"" not in r2.text else "FAIL"}')
        print(f'  success_msg: {"OK" if "lưu" in r2.text.lower() or "Da luu" in r2.text else "check flash"}')
    else:
        print('  save_hourly: skipped (no csrf or pending slot)')


def test_tp():
    print('=== tp.tb team report ===')
    s = session_for('tp.tb', '123123sS@')
    r = s.get(f'{BASE}/reports/team/', timeout=30)
    html = r.text
    print(f'  team_page: {"OK" if "jp-reports-page" in html else "FAIL"}')
    nhap_ho = re.findall(r'for_user=(\d+)', html)
    print(f'  nhap_ho_links: {len(nhap_ho)}')
    if nhap_ho:
        uid = nhap_ho[0]
        r2 = s.get(f'{BASE}/reports/today/?for_user={uid}', timeout=30)
        print(f'  nhap_ho_url: {r2.url}')
        print(f'  nhap_ho_badge: {"OK" if "Nh\u1eadp h\u1ed9 NV" in r2.text else "FAIL"}')
        print(f'  production_ui: {"OK" if "jp-prod-mobile-page" in r2.text else "FAIL"}')
        if 'today_office' in r2.text or 'office-sheet' in r2.text:
            print('  note: subordinate may be OFFICE profile not PRODUCTION')
    else:
        detail = re.findall(r'reports/(\d+)/', html)
        print(f'  detail_links: {len(detail)}')


if __name__ == '__main__':
    test_nv()
    print()
    test_tp()
