"""Find any remaining empty div/span with background styling (icon shells)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'tmp_prod_deploy', 'node_modules', '.git', '__pycache__'}
SKIP = {'templates/includes/portal_sidebar.html'}

EMPTY = re.compile(r'<(div|span)\b([^>]*)>(\s*(?:<!--[\s\S]*?-->\s*)*)</\1>', re.I | re.S)

def has_bg(attrs: str) -> bool:
    a = attrs.lower()
    return any(x in a for x in (
        'bg-hm', 'bg-light', 'bg-warning', 'bg-primary', 'bg-success', 'bg-info',
        'bg-danger', 'bg-secondary', 'bg-opacity', 'gradient', '-icon', 'icon-box',
        'rounded-circle', 'jp-reports-intro-leading',
    ))

total = 0
for p in sorted(ROOT.rglob('*.html')):
    if any(x in p.parts for x in SKIP_DIRS) or p.as_posix() in SKIP:
        continue
    t = p.read_text(encoding='utf-8')
    hits = []
    for m in EMPTY.finditer(t):
        if 'jp-theme-icon' in m.group(2) or 'jp-sidebar-collapse' in m.group(2):
            continue
        if has_bg(m.group(2)):
            hits.append(m.group(0)[:100].replace('\n', ' '))
    if hits:
        print(f'{p.as_posix()} ({len(hits)})')
        for h in hits[:4]:
            print(f'  {h}')
        total += len(hits)
print('total', total)
