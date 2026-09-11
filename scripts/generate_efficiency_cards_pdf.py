#!/usr/bin/env python3
"""PDF ngắn: giải thích 8 thẻ trên báo cáo năng suất SX."""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs' / 'Cong_thuc_tinh_hieu_suat_SX.pdf'


def register_fonts() -> None:
    win = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    regular = win / 'arial.ttf'
    bold = win / 'arialbd.ttf'
    if not regular.exists():
        regular = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        bold = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont('JP', str(regular)))
    pdfmetrics.registerFont(TTFont('JPb', str(bold)))


def main() -> None:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    hm = colors.HexColor('#c2410c')
    ink = colors.HexColor('#1f2937')
    muted = colors.HexColor('#6b7280')
    line = colors.HexColor('#e5e7eb')
    head = colors.HexColor('#fff7ed')

    title = ParagraphStyle(
        't', fontName='JPb', fontSize=16, leading=20,
        textColor=hm, alignment=TA_CENTER, spaceAfter=4,
    )
    sub = ParagraphStyle(
        's', fontName='JP', fontSize=9, leading=12,
        textColor=muted, alignment=TA_CENTER, spaceAfter=12,
    )
    th = ParagraphStyle(
        'th', fontName='JPb', fontSize=9.5, leading=12,
        textColor=ink, alignment=TA_LEFT,
    )
    td = ParagraphStyle(
        'td', fontName='JP', fontSize=9.5, leading=13,
        textColor=ink, alignment=TA_LEFT,
    )
    name = ParagraphStyle(
        'nm', fontName='JPb', fontSize=9.5, leading=12,
        textColor=hm, alignment=TA_LEFT,
    )
    note = ParagraphStyle(
        'n', fontName='JP', fontSize=8.5, leading=11,
        textColor=muted, alignment=TA_CENTER, spaceBefore=10,
    )

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title='8 the hieu suat SX',
    )

    story = [
        Paragraph('8 thẻ trên báo cáo năng suất SX', title),
        Paragraph('Giải thích cách tính — ngắn gọn', sub),
        HRFlowable(width='100%', thickness=1, color=hm, spaceAfter=10),
    ]

    rows = [[
        Paragraph('<b>Thẻ</b>', th),
        Paragraph('<b>Cách tính / lấy số</b>', th),
    ]]

    cards = [
        (
            '1. Hiệu suất TB trong ngày',
            'Hiệu suất sản lượng × Hiệu suất thời gian ÷ 100.',
        ),
        (
            '2. Hiệu suất sản lượng',
            '(HS công đoạn 1 × giờ 1 + HS công đoạn 2 × giờ 2 + …) '
            '÷ tổng giờ công đoạn.<br/>'
            'HS từng dòng đã là % — không nhân thêm 100, không cộng bù.',
        ),
        (
            '3. Hiệu suất thời gian',
            'Thời gian thực tế ÷ Thời gian làm việc × 100.<br/>'
            'Đo có dùng đủ giờ đã khai báo hay không.',
        ),
        (
            '4. Tổng hư hỏng',
            'Cộng tất cả số lượng hư hỏng của các công đoạn trong ngày.',
        ),
        (
            '5. Thời gian làm việc',
            'Số giờ công nhân <b>khai báo</b> khi gửi báo cáo (ví dụ 9,5 giờ).',
        ),
        (
            '6. Thời gian thực tế',
            'Cộng giờ của mọi công đoạn đã ghi trong ngày (kể cả công đoạn SL = 0).',
        ),
        (
            '7. Thời gian hao phí',
            'Thời gian làm việc − Thời gian thực tế.<br/>'
            'Phần giờ khai báo nhưng không gắn vào công đoạn nào.',
        ),
        (
            '8. Hiệu suất hỗ trợ',
            '((HS sau khi bù 1 × giờ 1 + HS sau khi bù 2 × giờ 2 + …) '
            '÷ tổng giờ công đoạn) × Hiệu suất thời gian ÷ 100.<br/>'
            'HS sau khi bù = HS + bù.',
        ),
    ]

    for label, how in cards:
        rows.append([
            Paragraph(label, name),
            Paragraph(how, td),
        ])

    table = Table(rows, colWidths=[4.2 * cm, 13 * cm])
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), head),
        ('GRID', (0, 0), (-1, -1), 0.45, line),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fcfcfc')))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Paragraph(
        'Ghi chú: Cột Bù hiệu suất giữ riêng, không cộng vào các thẻ hiệu suất ở trên.',
        note,
    ))

    doc.build(story)
    print(OUTPUT)


if __name__ == '__main__':
    main()
