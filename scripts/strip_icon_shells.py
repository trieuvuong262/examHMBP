"""Xóa thẻ bọc icon trống (nền màu) sau khi đã gỡ <i class="bi">."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_FILES = {'templates/includes/portal_sidebar.html'}
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

# class chứa chuỗi này → xóa nếu thẻ rỗng
ICON_SHELL_MARKERS = (
    'icon-box',
    'jp-home-block-icon',
    'jp-dashboard-item-icon',
    'jp-home-empty-icon',
    'jp-home-tools-group-icon',
    'jp-home-tool-mini-icon',
    'jp-home-tool-icon',
    'jp-home-tool-tile-icon',
    'jp-home-tool-arrow',
    'jp-home-tool-mini-arrow',
    'jp-tools-heading-icon',
    'jp-table-sort-icons',
    'jp-perm-module-icon',
    'jp-perm-submenu-icon',
    'jp-perm-members-head-icon',
    'jp-weekly-field-icon',
    'jp-weekly-link-card-icon',
    'jp-nas-root-icon',
    'jp-prod-section-label-icon',
    'jp-npl-transfer-loc-icon',
    'jp-doc-panel-empty-icon',
    'jp-login-lockout-icon',
    'guide-edit-section-icon',
    'jp-nas-share-open-icon',
)

MARKERS_ALT = '|'.join(re.escape(m) for m in ICON_SHELL_MARKERS)
EMPTY_ICON_SHELL = re.compile(
    rf'<(span|div)\b(?=[^>]*\bclass=["\'][^"\']*(?:{MARKERS_ALT})[^"\']*["\'])'
    r'[^>]*>\s*</\1>',
    re.IGNORECASE,
)


EMPTY_INPUT_GROUP_TEXT = re.compile(
    r'<span\s+class="input-group-text[^"]*">\s*</span>\s*',
    re.IGNORECASE,
)


def strip_shells(content: str) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return ''

    updated = EMPTY_ICON_SHELL.sub(repl, content)
    n_icon = n
    n = 0
    updated = EMPTY_INPUT_GROUP_TEXT.sub(repl, updated)
    return updated, n_icon + n


def main() -> int:
    total = 0
    files = 0
    for path in sorted(ROOT.rglob('*.html')):
        rel = path.relative_to(ROOT).as_posix()
        if any(p in SKIP_DIRS for p in path.parts) or rel in SKIP_FILES:
            continue
        original = path.read_text(encoding='utf-8')
        updated, n = strip_shells(original)
        if n:
            path.write_text(updated, encoding='utf-8', newline='\n')
            total += n
            files += 1
            print(f'  {rel}: -{n}')
    print(f'\nDone: {total} shells removed in {files} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
