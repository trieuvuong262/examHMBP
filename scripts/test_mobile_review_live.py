#!/usr/bin/env python3
import re
import requests

BASE = 'https://portal.justplay.vn'
s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
r = s.get(f'{BASE}/accounts/login/', timeout=30)
csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
s.post(
    f'{BASE}/accounts/login/',
    data={'csrfmiddlewaretoken': csrf, 'username': 'nv.tb', 'password': '123123sS@', 'next': '/reports/today/'},
    headers={'Referer': f'{BASE}/accounts/login/'},
    allow_redirects=True,
    timeout=30,
)
review = s.get(f'{BASE}/reports/today/?phase=review', timeout=30)
checks = {
    'css_v': 'reports-production-hourly.css?v=20260617g' in review.text,
    'js_v': 'reports-production-hourly.js?v=20260617g' in review.text,
    'review_sticky': 'jp-prod-review-sticky' in review.text,
    'review_page': 'jp-prod-mobile-page--review' in review.text,
    'grand_total_el': 'review-grand-total' in review.text,
    'save_btn': 'review-save-btn' in review.text,
    'submit_form': 'review-submit-form' in review.text,
    'no_save_draft': 'Lưu nháp' not in review.text,
    'no_continue': 'Tiếp tục nhập' not in review.text,
}
for k, v in checks.items():
    print(k, v)
