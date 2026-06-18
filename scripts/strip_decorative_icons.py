"""
Gỡ icon Bootstrap chỉ khi trang trí (icon trước chữ).
Giữ icon trong nút / link dạng btn / dropdown-toggle (có tương tác).

Luôn giữ nguyên: templates/includes/portal_sidebar.html
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_FILES = {'templates/includes/portal_sidebar.html'}
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

BI_ICON_TAG = re.compile(
    r'<i\s+[^>]*\bclass=["\'][^"\']*\bbi[\s-][^"\']*["\'][^>]*>\s*</i>',
    re.IGNORECASE,
)

A_OPEN = re.compile(r'<a\b[^>]*>', re.IGNORECASE)
BTN_OPEN = re.compile(r'<button\b[^>]*>', re.IGNORECASE)


def _tag_is_interactive_anchor(tag: str) -> bool:
    m = re.search(r'\bclass=["\']([^"\']*)["\']', tag, re.IGNORECASE)
    if not m:
        return False
    classes = m.group(1).lower().split()
    if 'btn' in classes or any(c.startswith('btn-') for c in classes):
        return True
    if 'dropdown-toggle' in classes:
        return True
    return False


def _tag_is_interactive_button(tag: str) -> bool:
    return bool(BTN_OPEN.match(tag))


def icon_is_interactive(html: str, icon_start: int) -> bool:
    before = html[:icon_start]
    last_btn_close = before.rfind('</button>')
    last_a_close = before.rfind('</a>')

    for m in BTN_OPEN.finditer(before):
        if m.start() <= last_btn_close:
            continue
        return True

    for m in A_OPEN.finditer(before):
        if m.start() <= last_a_close:
            continue
        if _tag_is_interactive_anchor(m.group(0)):
            return True

    return False


def strip_decorative_icons(content: str) -> tuple[str, int]:
    removed = 0
    lines_out: list[str] = []
    offset = 0
    for line in content.splitlines(keepends=True):
        def repl(m: re.Match) -> str:
            nonlocal removed
            pos = offset + m.start()
            if icon_is_interactive(content, pos):
                return m.group(0)
            removed += 1
            return ''

        lines_out.append(BI_ICON_TAG.sub(repl, line))
        offset += len(line)
    return ''.join(lines_out), removed


def iter_html_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob('*.html'):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel in SKIP_FILES:
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    total = 0
    changed = 0
    for path in iter_html_files():
        original = path.read_text(encoding='utf-8')
        updated, n = strip_decorative_icons(original)
        if n:
            path.write_text(updated, encoding='utf-8', newline='\n')
            changed += 1
            total += n
            print(f'  {path.relative_to(ROOT)}: -{n}')
    print(f'\nDone: {total} decorative icons removed in {changed} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
