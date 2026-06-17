"""Thêm ảnh minh họa cho từng bước trong templates/guide/inner/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INNER = ROOT / 'templates' / 'guide' / 'inner'

STEP_RE = re.compile(
    r'<div class="guide-step(?!\s*guide-step--illustrated)">\s*'
    r'<div class="guide-step-num">(\d+)</div>\s*'
    r'(<div[\s\S]*?</div>)\s*'
    r'</div>',
    re.MULTILINE,
)


def _img_name(section_id: str, index: int) -> str:
    return f'{section_id}-{index:02d}.png'


def _alt_text(section_id: str, index: int) -> str:
    return f'Minh họa bước {index} — {section_id.replace("-", " ")}'


def _render_step(section_id: str, index: int, body_html: str) -> str:
    img = _img_name(section_id, index)
    alt = _alt_text(section_id, index)
    body_escaped = body_html.replace('"', '&quot;') if False else body_html
    return (
        f'{{% include "guide/_step_with_img.html" with num={index} '
        f'img="{img}" alt="{alt}" body="{body_escaped}" %}}'
    )


def _render_step_safe(section_id: str, index: int, body_html: str) -> str:
    """Dùng block body trực tiếp — không qua include với body= (HTML phức tạp)."""
    img = _img_name(section_id, index)
    alt = _alt_text(section_id, index)
    return (
        f'<div class="guide-step guide-step--illustrated">\n'
        f'    <div class="guide-step-head">\n'
        f'        <div class="guide-step-num">{index}</div>\n'
        f'        <div class="guide-step-body">{body_html.strip()}</div>\n'
        f'    </div>\n'
        f'    <figure class="guide-step-figure">\n'
        f'        <img src="{{% static \'images/guide/{img}\' %}}" alt="{alt}" '
        f'class="guide-zoomable" loading="lazy">\n'
        f'    </figure>\n'
        f'</div>'
    )


def transform_html(section_id: str, html: str) -> str:
    counter = 0

    def repl(match: re.Match) -> str:
        nonlocal counter
        counter += 1
        body = match.group(2)
        return _render_step_safe(section_id, counter, body)

    out = STEP_RE.sub(repl, html)

    # Bỏ figure lớn trùng trong guide-split (đã có ảnh từng bước)
    out = re.sub(
        r'<div class="guide-split[^"]*">(\s*<div class="guide-steps">[\s\S]*?</div>)\s*'
        r'<figure class="guide-figure">[\s\S]*?</figure>\s*</div>',
        r'<div class="guide-steps mb-4">\1</div>',
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'<figure class="guide-figure mb-[34]">[\s\S]*?</figure>\s*',
        '',
        out,
        count=1,
    )

    if '{% load static %}' not in out:
        out = '{% load static %}\n' + out

    return out


def transform_faq(html: str) -> str:
    """Chuyển FAQ dl/dt thành các bước có ảnh."""
    if 'guide-step--illustrated' in html:
        return html

    items = re.findall(
        r'<dt class="fw-bold[^"]*">(.*?)</dt>\s*<dd class="[^"]*">(.*?)</dd>',
        html,
        re.DOTALL,
    )
    if not items:
        return html

    steps = []
    for i, (q, a) in enumerate(items, 1):
        body = f'<p class="fw-bold mb-2">{q.strip()}</p><div>{a.strip()}</div>'
        steps.append(_render_step_safe('faq', i, body))

    block = '<div class="guide-steps mb-0">\n' + '\n'.join(steps) + '\n</div>'
    html = re.sub(r'<dl class="mb-0">[\s\S]*?</dl>', block, html)
    if '{% load static %}' not in html:
        html = '{% load static %}\n' + html
    return html


def transform_intro_sections(html: str, section_id: str) -> str:
    """gioi-thieu, chuan-bi — chuyển nội dung list thành bước có ảnh."""
    if section_id == 'gioi-thieu' and 'guide-step--illustrated' not in html:
        steps = [
            ('<p><strong>JustPlay Portal</strong> là cổng thông tin nội bộ. Menu chỉ hiện module bạn được phân quyền.</p>', 1),
            ('<p>Các module phổ biến: Thông báo, Báo cáo, Đào tạo, Kiểm tra, Công việc, Tài liệu — tùy nhóm quyền của bạn.</p>', 2),
            ('<p>Trang chủ hiển thị lời chào và các ô truy cập nhanh theo quyền.</p>', 3),
            ('<p>HR / IT thường có thêm: Nhân sự, Phân quyền, Quản trị hệ thống.</p>', 4),
        ]
        rendered = '\n'.join(_render_step_safe(section_id, n, b) for b, n in steps)
        return '{% load static %}\n<div class="guide-steps mb-0">\n' + rendered + '\n</div>'

    if section_id == 'chuan-bi' and 'guide-step--illustrated' not in html:
        steps = [
            ('<p><strong>Tài khoản</strong> do HR/IT cấp — username + mật khẩu tạm.</p>', 1),
            ('<p><strong>Internet</strong> — Wi-Fi công ty hoặc 4G ổn định.</p>', 2),
            ('<p><strong>Trình duyệt</strong> Chrome, Safari, Edge bản mới. Tránh trình duyệt quá cũ trên điện thoại.</p>', 3),
            ('<p>Username dạng <code>nam.nt</code>, email <code>nam.nt@justplay.vn</code>. Lần đầu đăng nhập bắt buộc đổi mật khẩu.</p>', 4),
        ]
        rendered = '\n'.join(_render_step_safe(section_id, n, b) for b, n in steps)
        return '{% load static %}\n<div class="guide-steps mb-0">\n' + rendered + '\n</div>'

    return html


def main():
    for path in sorted(INNER.glob('*.html')):
        section_id = path.stem
        html = path.read_text(encoding='utf-8')
        if section_id in ('gioi-thieu', 'chuan-bi'):
            html = transform_intro_sections(html, section_id)
        elif section_id == 'faq':
            html = transform_faq(html)
        else:
            html = transform_html(section_id, html)
        path.write_text(html.rstrip() + '\n', encoding='utf-8')
        step_count = html.count('guide-step--illustrated')
        print(f'{section_id}: {step_count} steps with images')


if __name__ == '__main__':
    main()
