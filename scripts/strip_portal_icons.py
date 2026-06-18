"""
Remove Bootstrap Icons (<i class="bi ...">) from portal HTML templates.

Keeps icons only in:
  - templates/includes/portal_sidebar.html (menu + menu con)
  - base.html: nút mở menu mobile (bi-list trong jp-topbar-menu-btn)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_FILES = {
    'templates/includes/portal_sidebar.html',
}

SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

# <i class="...bi..."></i> — class có thể chứa bi bi-xxx hoặc bi-xxx
BI_ICON_TAG = re.compile(
    r'<i\s+[^>]*\bclass=["\'][^"\']*\bbi[\s-][^"\']*["\'][^>]*>\s*</i>',
    re.IGNORECASE,
)

# base.html: giữ icon hamburger menu mobile
KEEP_ICON_IN_LINE = re.compile(
    r'jp-topbar-menu-btn|data-bs-target="#mobileSidebar"',
)


def should_keep_icon(tag: str, line: str) -> bool:
    if 'bi-list' in tag and KEEP_ICON_IN_LINE.search(line):
        return True
    return False


def strip_icons_from_content(content: str) -> tuple[str, int]:
    removed = 0
    lines_out: list[str] = []
    for line in content.splitlines(keepends=True):
        def repl(m: re.Match) -> str:
            nonlocal removed
            if should_keep_icon(m.group(0), line):
                return m.group(0)
            removed += 1
            return ''

        new_line = BI_ICON_TAG.sub(repl, line)
        # Khoảng trắng thừa ngay sau khi xóa icon trên cùng dòng
        new_line = re.sub(r'(\S)\s{2,}', r'\1 ', new_line)
        new_line = re.sub(r'>\s{2,}', '> ', new_line)
        lines_out.append(new_line)
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
    total_removed = 0
    changed_files = 0
    for path in iter_html_files():
        original = path.read_text(encoding='utf-8')
        updated, n = strip_icons_from_content(original)
        if n:
            path.write_text(updated, encoding='utf-8', newline='\n')
            changed_files += 1
            total_removed += n
            print(f'  {path.relative_to(ROOT)}: -{n}')
    print(f'\nDone: {total_removed} icons removed in {changed_files} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
