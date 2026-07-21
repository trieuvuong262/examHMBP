from pathlib import Path
import re

from patch_sx_list_grids import PATCHES, enrich_td_open

ROOT = Path(__file__).resolve().parents[1] / 'san_xuat' / 'templates' / 'san_xuat'


def strip_td_attrs(row: str) -> str:
    def repl(m):
        body = m.group(1) or ''
        body = re.sub(r'\s*class="[^"]*"', '', body)
        body = re.sub(r'\s*data-col="[^"]*"', '', body)
        body = body.strip()
        return '<td>' if not body else f'<td {body}>'

    return re.sub(r'<td(\s[^>]*)?>', repl, row)


def retag_row(row: str, spec: dict) -> str:
    keys = list(spec['cols'])
    if spec.get('actions', False):
        keys.append('actions')
    row = strip_td_attrs(row)
    parts = re.split(r'(<td[^>]*>)', row)
    out = []
    key_i = 0
    for part in parts:
        if part.startswith('<td'):
            if key_i < len(keys):
                out.append(enrich_td_open(part, keys[key_i]))
                key_i += 1
            else:
                out.append(part)
        else:
            out.append(part)
    return ''.join(out)


def main():
    for name, spec in PATCHES.items():
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        m = re.search(r'{% for \w+ in \w+ %}.*?<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
        if not m:
            continue
        old = m.group(1)
        new = retag_row(old, spec)
        if new != old:
            text = text.replace(old, new, 1)
            path.write_text(text, encoding='utf-8')
            print('retagged', name)


if __name__ == '__main__':
    main()
