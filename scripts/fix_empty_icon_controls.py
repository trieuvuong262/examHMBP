"""Sau khi gỡ icon: khôi phục nút/link trống bằng text từ title hoặc aria-label."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_FILES = {'templates/includes/portal_sidebar.html'}
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

EMPTY_CONTROL = re.compile(
    r'(<(button|a)\b(?=[^>]*\b(?:title|aria-label)=)(?:(?!>).)*>)'
    r'(\s*)'
    r'(</\2>)',
    re.IGNORECASE | re.DOTALL,
)

TITLE_RE = re.compile(r'\btitle="([^"]*)"', re.IGNORECASE)
ARIA_RE = re.compile(r'\baria-label="([^"]*)"', re.IGNORECASE)


def label_from_opening_tag(tag: str) -> str:
    m = TITLE_RE.search(tag)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = ARIA_RE.search(tag)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return ''


def fix_content(content: str) -> tuple[str, int]:
    fixed = 0

    def repl(m: re.Match) -> str:
        nonlocal fixed
        opening, _tag, inner, closing = m.group(1), m.group(2), m.group(3), m.group(4)
        if inner.strip():
            return m.group(0)
        label = label_from_opening_tag(opening)
        if not label:
            return m.group(0)
        fixed += 1
        return f'{opening}{label}{closing}'

    return EMPTY_CONTROL.sub(repl, content), fixed


def main() -> int:
    total = 0
    for path in sorted(ROOT.rglob('*.html')):
        rel = path.relative_to(ROOT).as_posix()
        if any(p in SKIP_DIRS for p in path.parts) or rel in SKIP_FILES:
            continue
        original = path.read_text(encoding='utf-8')
        updated, n = fix_content(original)
        if n:
            path.write_text(updated, encoding='utf-8', newline='\n')
            total += n
            print(f'  {rel}: +{n} labels')
    print(f'\nDone: {total} controls labeled')
    return 0


if __name__ == '__main__':
    sys.exit(main())
