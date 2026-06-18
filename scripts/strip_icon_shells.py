"""Xóa khung nền icon trống sau khi gỡ icon trang trí."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_FILES = {'templates/includes/portal_sidebar.html'}
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

KEEP_CLASS = re.compile(
    r'\b(jp-theme-icon-|jp-sidebar-collapse-icon)',
    re.IGNORECASE,
)

EMPTY_EL = re.compile(
    r'<(div|span)\b([^>]*)>(\s*(?:<!--[\s\S]*?-->\s*)*)</\1>',
    re.IGNORECASE | re.DOTALL,
)

EMPTY_INPUT_GROUP_TEXT = re.compile(
    r'<span\s+class="input-group-text[^"]*">\s*(?:<!--[\s\S]*?-->\s*)*</span>\s*',
    re.IGNORECASE | re.DOTALL,
)

STAT_CARD_MS3 = re.compile(
    r'(<div class="d-flex align-items-center">\s*)<div class="ms-3">',
    re.IGNORECASE,
)

# Vòng tròn cố định (inline width/height) — icon đã gỡ
FIXED_ICON_CIRCLE = re.compile(
    r'<div\b[^>]*\brounded-circle\b[^>]*\bstyle="[^"]*(?:width|height)\s*:\s*\d+px[^"]*"[^>]*>'
    r'\s*(?:{%[^%]*%}\s*)*</div>\s*',
    re.IGNORECASE | re.DOTALL,
)

# Placeholder ảnh / icon full-size trống
EMPTY_PLACEHOLDER = re.compile(
    r'<div\b[^>]*\bw-100\s+h-100\b[^>]*\bd-flex\b[^>]*\b(?:align-items-center|justify-content-center)\b[^>]*>'
    r'\s*</div>\s*',
    re.IGNORECASE | re.DOTALL,
)

# Vòng tròn trống phổ biến (bootstrap bg-*)
EMPTY_ROUNDED_BG = re.compile(
    r'<div\b[^>]*\bclass="[^"]*(?:'
    r'bg-(?:hm|primary|success|warning|info|danger|light|secondary)(?:-subtle|-light)?|bg-opacity-10'
    r')[^"]*rounded-circle[^"]*"[^>]*>\s*</div>\s*',
    re.IGNORECASE | re.DOTALL,
)


def is_decorative_icon_shell(attrs: str) -> bool:
    if KEEP_CLASS.search(attrs):
        return False
    a = attrs.lower()
    if re.search(r'class="[^"]*-icon', a):
        return True
    if 'icon-box' in a:
        return True
    if 'rounded-circle' in a:
        if any(x in a for x in (
            'bg-opacity', 'bg-hm', 'bg-warning', 'bg-primary', 'bg-success',
            'bg-light', 'bg-hm-subtle', 'bg-hm-light',
        )):
            return True
        if re.search(r'\bp-[23]\b', a):
            return True
    return False


def strip_shells(content: str) -> tuple[str, int]:
    total = 0

    def sub_count(pattern: re.Pattern[str], text: str) -> tuple[str, int]:
        n = 0

        def repl(_m: re.Match) -> str:
            nonlocal n
            n += 1
            return ''

        return pattern.sub(repl, text), n

    def repl_empty(m: re.Match) -> str:
        nonlocal total
        if not is_decorative_icon_shell(m.group(2)):
            return m.group(0)
        total += 1
        return ''

    updated = EMPTY_EL.sub(repl_empty, content)

    updated, n = sub_count(EMPTY_INPUT_GROUP_TEXT, updated)
    total += n

    updated, n = sub_count(EMPTY_ROUNDED_BG, updated)
    total += n

    updated, n = sub_count(FIXED_ICON_CIRCLE, updated)
    total += n

    updated, n = sub_count(EMPTY_PLACEHOLDER, updated)
    total += n

    n = 0

    def repl_ms3(m: re.Match) -> str:
        nonlocal n, total
        n += 1
        total += 1
        return f'{m.group(1)}<div>'

    updated = STAT_CARD_MS3.sub(repl_ms3, updated)

    return updated, total


def iter_html_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob('*.html'):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts) or rel in SKIP_FILES:
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    grand = 0
    files = 0
    for path in iter_html_files():
        original = path.read_text(encoding='utf-8')
        updated, n = strip_shells(original)
        if n:
            path.write_text(updated, encoding='utf-8', newline='\n')
            grand += n
            files += 1
            print(f'  {path.relative_to(ROOT)}: -{n}')
    print(f'\nDone: {grand} shells removed in {files} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
