import re
from pathlib import Path

INNER = Path(__file__).resolve().parents[1] / 'templates' / 'guide' / 'inner'
for path in INNER.glob('*.html'):
    html = path.read_text(encoding='utf-8')
    orig = html
    html = re.sub(
        r'<div class="guide-steps mb-4">\s*<div class="guide-steps">',
        '<div class="guide-steps mb-4">',
        html,
    )
    html = re.sub(
        r'</div>\s*</div>(\s*\n<div class="guide-tip)',
        r'</div>\1',
        html,
    )
    if html != orig:
        path.write_text(html, encoding='utf-8')
        print('fixed', path.name)
