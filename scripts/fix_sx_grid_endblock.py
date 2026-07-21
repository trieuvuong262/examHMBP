from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / 'san_xuat' / 'templates' / 'san_xuat'
pat = re.compile(
    r"\{% endblock %\}\s*\{% include 'san_xuat/includes/sx_list_grid_scripts.html' %\}\s*\{% endblock %\}",
    re.MULTILINE,
)
repl = "{% include 'san_xuat/includes/sx_list_grid_scripts.html' %}\n{% endblock %}"
for p in root.glob('*.html'):
    t = p.read_text(encoding='utf-8')
    new = pat.sub(repl, t)
    if new != t:
        p.write_text(new, encoding='utf-8')
        print('fixed', p.name)
