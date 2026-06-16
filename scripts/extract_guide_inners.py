"""Trích nội dung accordion-body sang templates/guide/inner/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'templates' / 'guide' / '_default_body.html.bak'
EXTRA = ROOT / 'templates' / 'guide' / '_extra_sections.html'
OUT = ROOT / 'templates' / 'guide' / 'inner'

SECTION_IDS = [
    'bat-dau', 'gioi-thieu', 'chuan-bi', 'dang-nhap', 'doi-mat-khau',
    'phan-quyen', 'thong-bao', 'bao-cao', 'kpi', 'dao-tao', 'kiem-tra',
    'tai-lieu', 'cong-viec', 'de-xuat', 'ho-tro', 'thiet-bi', 'gop-y',
    'kho-npl', 'kiotviet', 'nas', 'tuyen-dung', 'quan-tri', 'quan-tri-he-thong', 'faq',
]


def extract_body(html: str, section_id: str) -> str | None:
    marker = f'id="{section_id}"'
    start = html.find(marker)
    if start < 0:
        return None
    body_tag = 'class="accordion-body"'
    body_start = html.find(body_tag, start)
    if body_start < 0:
        return None
    content_start = html.find('>', body_start) + 1
    depth = 1
    i = content_start
    while i < len(html) and depth > 0:
        next_open = html.find('<div', i)
        next_close = html.find('</div>', i)
        if next_close < 0:
            break
        if next_open >= 0 and next_open < next_close:
            depth += 1
            i = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html[content_start:next_close].strip()
            i = next_close + 6
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    html = SRC.read_text(encoding='utf-8')
    extra = EXTRA.read_text(encoding='utf-8') if EXTRA.exists() else ''
    combined = html + '\n' + extra
    count = 0
    for sid in SECTION_IDS:
        body = extract_body(combined, sid)
        if body:
            (OUT / f'{sid}.html').write_text(body + '\n', encoding='utf-8')
            print('ok', sid)
            count += 1
        else:
            print('skip', sid)
    print('total', count)


if __name__ == '__main__':
    main()
