from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / 'san_xuat' / 'templates' / 'san_xuat'
inc = "{% include 'san_xuat/includes/sx_list_grid_scripts.html' %}\n"
for p in root.glob('*.html'):
    t = p.read_text(encoding='utf-8')
    if 'sx_list_grid_scripts' not in t:
        continue
    orig = t
    t = re.sub(r"\n?{% include 'san_xuat/includes/sx_list_grid_scripts.html' %}\n?", '\n', t)
    if inc.strip() not in t:
        t = t.rstrip() + '\n' + inc + '{% endblock %}\n'
    if t != orig:
        p.write_text(t, encoding='utf-8')
        print('fixed', p.name)
