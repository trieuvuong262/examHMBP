#!/usr/bin/env python3
"""Audit guide templates and live portal page."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def audit_templates():
    inner = ROOT / "templates" / "guide" / "inner"
    print("=== LOCAL TEMPLATE AUDIT ===")
    for f in sorted(inner.glob("*.html")):
        t = f.read_text(encoding="utf-8")
        nested = len(re.findall(r'<div class="guide-steps">[\s\S]*?<div class="guide-steps">', t))
        steps = t.count("guide-step--illustrated")
        imgs = len(re.findall(r"images/guide/([^'\"]+)", t))
        flags = []
        if nested:
            flags.append(f"nested={nested}")
        if steps and steps != imgs:
            flags.append(f"steps={steps} imgs={imgs}")
        if flags:
            print(f"  {f.stem}: {', '.join(flags)}")


def audit_live():
    from playwright.sync_api import sync_playwright

    base = "https://portal.justplay.vn"
    print("\n=== LIVE PAGE (admin) ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/accounts/login/", wait_until="networkidle", timeout=60000)
        page.fill("input[name=username]", "admin")
        page.fill("input[name=password]", "123123sS")
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.goto(f"{base}/huong-dan/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        data = page.evaluate(
            """() => {
            const toc = [...document.querySelectorAll('#guideDesktopToc .guide-toc-link')]
                .map(a => ({text: a.textContent.trim(), href: a.getAttribute('href')}));
            const sections = [...document.querySelectorAll('.guide-accordion .accordion-item')].map(el => {
                const btn = el.querySelector('.accordion-button');
                const target = btn ? btn.getAttribute('data-bs-target') : '';
                const id = target ? target.replace('#guide-c-', '') : '';
                return {
                    id,
                    title: btn ? btn.textContent.trim() : '',
                    steps: el.querySelectorAll('.guide-step--illustrated').length,
                    imgs: el.querySelectorAll('.guide-step-figure img').length,
                    nested: el.querySelectorAll('.guide-steps .guide-steps').length,
                    textLen: (el.querySelector('.accordion-body') || {}).textContent?.length || 0,
                };
            });
            const imgs = [...document.querySelectorAll('.guide-step-figure img')];
            const broken = imgs.filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src);
            return {
                toc,
                sections,
                nestedTotal: document.querySelectorAll('.guide-steps .guide-steps').length,
                totalSteps: document.querySelectorAll('.guide-step--illustrated').length,
                totalImgs: imgs.length,
                broken,
            };
        }"""
        )

        print("TOC:")
        for i, item in enumerate(data["toc"], 1):
            print(f"  {i}. {item['text']} -> {item['href']}")

        print(f"\nTotal illustrated steps: {data['totalSteps']}, images: {data['totalImgs']}")
        print(f"Nested guide-steps: {data['nestedTotal']}")
        print(f"Broken images: {len(data['broken'])}")
        for src in data["broken"][:10]:
            print(f"  - {src}")

        print("\nSection issues:")
        for s in data["sections"]:
            issues = []
            if s["nested"]:
                issues.append(f"nested={s['nested']}")
            if s["steps"] != s["imgs"]:
                issues.append(f"steps={s['steps']} imgs={s['imgs']}")
            if s["textLen"] < 50:
                issues.append(f"short content ({s['textLen']} chars)")
            if issues:
                print(f"  {s['id']}: {', '.join(issues)}")

        browser.close()


if __name__ == "__main__":
    audit_templates()
    audit_live()
