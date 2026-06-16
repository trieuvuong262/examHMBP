#!/usr/bin/env python3
"""Kiểm tra mục lục Hướng dẫn theo quyền từng user trên portal."""

from __future__ import annotations

import json
import sys

BASE_URL = 'https://portal.justplay.vn'
USERS = [
    ('nvmoi', '123123sS@'),
    ('vuonglnt', '123123sS@'),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('pip install playwright && playwright install chromium', file=sys.stderr)
        sys.exit(1)

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale='vi-VN',
            viewport={'width': 1280, 'height': 900},
            ignore_https_errors=True,
        )

        for username, password in USERS:
            context.clear_cookies()
            page = context.new_page()
            print(f'\n=== {username} ===')

            page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle', timeout=60000)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state('networkidle')

            if 'login' in page.url.lower():
                print('  LOGIN FAILED')
                results[username] = {'error': 'login_failed'}
                page.close()
                continue

            print(f'  after login: {page.url}')

            page.goto(BASE_URL + '/huong-dan/', wait_until='networkidle', timeout=60000)
            final_url = page.url
            title = page.title()
            redirected = final_url.rstrip('/') != (BASE_URL + '/huong-dan').rstrip('/')

            if redirected:
                print(f'  REDIRECTED from /huong-dan/ -> {final_url}')
                results[username] = {
                    'error': 'no_guide_permission',
                    'redirected_from_guide': True,
                    'url': final_url,
                }
                page.close()
                continue

            try:
                page.wait_for_selector('.jp-guide-page, .jp-page', timeout=15000)
            except Exception:
                snippet = page.locator('body').inner_text()[:500]
                results[username] = {
                    'error': 'no_guide_page',
                    'url': final_url,
                    'title': title,
                    'body_preview': snippet,
                }
                print(f'  NO GUIDE PAGE — url={final_url}')
                print(f'  body: {snippet[:200]}...')
                page.close()
                continue

            toc_links = page.locator('#guideDesktopToc .guide-toc-link')
            toc_items = []
            for i in range(toc_links.count()):
                toc_items.append({
                    'label': toc_links.nth(i).inner_text().strip(),
                    'href': toc_links.nth(i).get_attribute('href') or '',
                })

            has_sidebar = page.locator('#guideDesktopToc').count() > 0
            has_accordion = page.locator('#guideAccordion').count() > 0
            has_db_prose = page.locator('.guide-prose').count() > 0

            section_ids = page.eval_on_selector_all(
                '.accordion-item[id]',
                'els => els.map(e => e.id)',
            )

            notice = ''
            el = page.locator('.jp-guide-page .alert-light')
            if el.count():
                notice = el.first.inner_text().strip()

            results[username] = {
                'url': final_url,
                'redirected_from_guide': redirected,
                'toc_count': len(toc_items),
                'toc': toc_items,
                'section_ids': section_ids,
                'has_sidebar': has_sidebar,
                'has_accordion': has_accordion,
                'has_db_prose': has_db_prose,
                'notice': notice,
            }

            print(f'  TOC ({len(toc_items)} mục):')
            for item in toc_items:
                print(f'    - {item["label"]} {item["href"]}')
            print(f'  Sections trong body ({len(section_ids)}): {", ".join(section_ids)}')

            page.close()

        browser.close()

    print('\n=== JSON ===')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
