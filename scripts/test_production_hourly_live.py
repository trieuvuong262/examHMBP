#!/usr/bin/env python3
"""E2E smoke test báo cáo SX trên portal live."""
import re
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('SKIP: playwright not installed')
    sys.exit(0)

BASE = 'https://portal.justplay.vn'
USERS = [
    ('nv.tb', '123123sS@', 'employee'),
    ('tp.tb', '123123sS@', 'supervisor'),
]


def login(page, username, password):
    page.goto(f'{BASE}/accounts/login/', wait_until='networkidle')
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')


def test_user(username, password, role):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 390, 'height': 844})
        page = context.new_page()
        try:
            login(page, username, password)
            if '/accounts/login' in page.url:
                return [f'{username}: LOGIN FAILED url={page.url}']

            page.goto(f'{BASE}/reports/today/', wait_until='networkidle')
            html = page.content()
            results.append(f'{username}: reports/today status OK url={page.url}')

            if 'today_production_hourly' in html or 'jp-prod-mobile-page' in html:
                results.append(f'{username}: production hourly UI detected')
            elif 'today.html' in html or 'lines-table' in html:
                results.append(f'{username}: OLD production form (not hourly)')
            else:
                results.append(f'{username}: office or other report form')

            backdrops = page.locator('.modal-backdrop').count()
            hourly_visible = page.locator('#hourlyModal.show, #hourlyModal[style*="display: block"]').count()
            body_modal = 'modal-open' in (page.evaluate('document.body.className') or '')
            results.append(
                f'{username}: backdrops={backdrops} hourly_modal_show={hourly_visible} body_modal_open={body_modal}'
            )

            if backdrops > 0 and hourly_visible == 0:
                results.append(f'{username}: BUG blur — backdrop without visible modal')

            modal_display = page.evaluate("""() => {
                const m = document.getElementById('hourlyModal');
                if (!m) return 'no-modal';
                const s = window.getComputedStyle(m);
                return `display=${s.display} opacity=${s.opacity} class=${m.className}`;
            }""")
            results.append(f'{username}: hourlyModal {modal_display}')

            if role == 'supervisor':
                page.goto(f'{BASE}/reports/team/', wait_until='networkidle')
                team_html = page.content()
                nhap_ho = 'Nhập hộ' in team_html
                results.append(f'{username}: team page Nhập hộ={nhap_ho}')
                link = page.locator('a.btn:has-text("Nhập hộ")').first
                if link.count():
                    href = link.get_attribute('href') or ''
                    results.append(f'{username}: nhap_ho href={href}')
                    if href:
                        dest = BASE + href if href.startswith('/') else href
                        page.goto(dest, wait_until='networkidle')
                    results.append(f'{username}: nhap_ho url={page.url}')
                    results.append(f'{username}: nhap_ho hourly={"jp-prod-mobile-page" in page.content()}')
                    bd = page.locator('.modal-backdrop').count()
                    mv = page.locator('#hourlyModal.show').count()
                    results.append(f'{username}: nhap_ho backdrops={bd} modal_show={mv}')
                    if bd > 0 and mv == 0:
                        results.append(f'{username}: nhap_ho BUG blur')
        except Exception as exc:
            results.append(f'{username}: ERROR {exc}')
        finally:
            browser.close()
    return results


def main():
    all_lines = []
    for user, pwd, role in USERS:
        all_lines.extend(test_user(user, pwd, role))
    for line in all_lines:
        print(line)
    if any('BUG blur' in l or 'LOGIN FAILED' in l or 'ERROR' in l for l in all_lines):
        sys.exit(1)


if __name__ == '__main__':
    main()
