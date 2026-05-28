"""Normalize button classes across HTML templates."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = [
    (r'\s+rounded-pill(?=\s|"|\'|$)', ''),
    (r'\s+rounded-2(?=\s|"|\'|$)', ''),
    (r'\s+rounded-3(?=\s|"|\'|$)', ''),
    (r'\s+rounded-4(?=\s|"|\'|$)', ''),
    (r'btn btn-primary', 'btn btn-hm'),
    (r'btn btn-success', 'btn btn-hm'),
    (r'btn btn-info', 'btn btn-hm'),
    (r'btn btn-warning(?!\s+text-dark)', 'btn btn-hm-dark'),
    (r'btn btn-outline-primary', 'btn btn-outline-hm'),
    (r'btn btn-outline-success', 'btn btn-outline-hm'),
    (r'btn btn-outline-info', 'btn btn-outline-hm'),
    (r'btn btn-outline-secondary', 'btn btn-outline-dark'),
    (r'btn-login', 'btn btn-hm'),
    (r'btn-hm-save', 'btn btn-hm'),
    (r'btn btn-hm-dark text-dark', 'btn btn-hm-dark'),
    (r'jp-kanban-toolbar', 'kanban-toolbar jp-kanban-toolbar'),
]


def main():
    updated = 0
    for path in ROOT.rglob('*.html'):
        if '.git' in path.parts:
            continue
        text = path.read_text(encoding='utf-8')
        orig = text
        for pattern, repl in REPLACEMENTS:
            text = re.sub(pattern, repl, text)
        if text != orig:
            path.write_text(text, encoding='utf-8')
            print(f'updated: {path.relative_to(ROOT)}')
            updated += 1
    print(f'done — {updated} files updated')


if __name__ == '__main__':
    main()
