"""Scan HTML for empty icon background shells."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'templates/includes/portal_sidebar.html'}
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}

# Empty element: only whitespace/comments inside
EMPTY_TAG = re.compile(
    r'<(span|div|i)\b([^>]*)>(\s*(?:<!--.*?-->\s*)*)</\1>',
    re.IGNORECASE | re.DOTALL,
)

ICON_CLASS = re.compile(
    r'\bclass=["\'][^"\']*(?:'
    r'icon-box|icon-shell|[-_]icon(?:-|["\s\'])|input-group-text'
    r')[^"\']*["\']',
    re.IGNORECASE,
)

INPUT_GROUP_EMPTY = re.compile(
    r'<span\s+class="input-group-text[^"]*">\s*(?:<!--.*?-->\s*)*</span>',
    re.IGNORECASE | re.DOTALL,
)


def scan_file(path: Path) -> list[str]:
    hits: list[str] = []
    text = path.read_text(encoding='utf-8')
    for m in EMPTY_TAG.finditer(text):
        attrs = m.group(2)
        if not ICON_CLASS.search(attrs):
            continue
        snippet = m.group(0).replace('\n', ' ')[:120]
        hits.append(snippet)
    for m in INPUT_GROUP_EMPTY.finditer(text):
        snippet = m.group(0).replace('\n', ' ')[:120]
        if snippet not in hits:
            hits.append(snippet)
    return hits


def main() -> None:
    total = 0
    for path in sorted(ROOT.rglob('*.html')):
        rel = path.relative_to(ROOT).as_posix()
        if any(p in SKIP_DIRS for p in path.parts) or rel in SKIP:
            continue
        hits = scan_file(path)
        if hits:
            total += len(hits)
            print(f'\n{rel} ({len(hits)})')
            for h in hits[:8]:
                print(f'  {h}')
            if len(hits) > 8:
                print(f'  ... +{len(hits) - 8} more')
    print(f'\nTotal empty icon shells: {total}')


if __name__ == '__main__':
    main()
