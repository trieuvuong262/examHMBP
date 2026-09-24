#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF hướng dẫn Công việc: cá nhân · dự án nội bộ · liên phòng ban.

Chạy:
  python scripts/generate_cong_viec_guide_pdf.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / 'static' / 'images' / 'guide'
OUTPUT = ROOT / 'docs' / 'Huong_dan_Cong_viec_Nhan_vien_va_Quan_ly.pdf'

FONT = 'JPBody'
FONT_BOLD = 'JPBodyBold'
IMG_MAX_W = 16.2 * cm
IMG_MAX_H = 11.2 * cm

BRAND = colors.HexColor('#dc2626')
INK = colors.HexColor('#334155')
MUTED = colors.HexColor('#64748b')
HEAD = colors.HexColor('#1e293b')
TIP_BG = colors.HexColor('#eff6ff')
TIP_FG = colors.HexColor('#1e40af')
DEMO_BG = colors.HexColor('#fefce8')
DEMO_FG = colors.HexColor('#854d0e')
ROW_ALT = colors.HexColor('#f8fafc')
HDR = colors.HexColor('#1e293b')

TODAY = date.today()
DUE = TODAY + timedelta(days=15)


def register_fonts():
    win = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    reg, bold = win / 'arial.ttf', win / 'arialbd.ttf'
    if not reg.exists():
        reg = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        bold = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont(FONT, str(reg)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))


def styles():
    return {
        'title': ParagraphStyle(
            't', fontName=FONT_BOLD, fontSize=18, leading=24,
            textColor=BRAND, alignment=TA_CENTER, spaceAfter=6,
        ),
        'subtitle': ParagraphStyle(
            'st', fontName=FONT, fontSize=10.5, leading=14,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=4,
        ),
        'h1': ParagraphStyle(
            'h1', fontName=FONT_BOLD, fontSize=13.5, leading=17,
            textColor=BRAND, spaceBefore=10, spaceAfter=6,
        ),
        'h2': ParagraphStyle(
            'h2', fontName=FONT_BOLD, fontSize=11, leading=14,
            textColor=HEAD, spaceBefore=8, spaceAfter=4,
        ),
        'body': ParagraphStyle(
            'b', fontName=FONT, fontSize=10, leading=14,
            textColor=INK, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        'bullet': ParagraphStyle(
            'bu', fontName=FONT, fontSize=10, leading=13.5,
            textColor=INK, leftIndent=12, spaceAfter=2,
        ),
        'step': ParagraphStyle(
            'step', fontName=FONT_BOLD, fontSize=10.5, leading=14,
            textColor=BRAND, spaceBefore=6, spaceAfter=2,
        ),
        'caption': ParagraphStyle(
            'cap', fontName=FONT, fontSize=8.5, leading=11,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=6,
        ),
        'tip': ParagraphStyle(
            'tip', fontName=FONT, fontSize=9.5, leading=13,
            textColor=TIP_FG, backColor=TIP_BG,
            borderPadding=7, leftIndent=3, rightIndent=3, spaceBefore=4, spaceAfter=6,
        ),
        'demo': ParagraphStyle(
            'demo', fontName=FONT, fontSize=9.5, leading=13,
            textColor=DEMO_FG, backColor=DEMO_BG,
            borderPadding=7, leftIndent=3, rightIndent=3, spaceBefore=4, spaceAfter=6,
        ),
        'cell': ParagraphStyle('cell', fontName=FONT, fontSize=8.5, leading=11, textColor=INK),
        'cellb': ParagraphStyle('cellb', fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=INK),
        'cellh': ParagraphStyle('cellh', fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.white),
    }


def P(text, key, st):
    return Paragraph(str(text).replace('\n', '<br/>'), st[key])


def bullets(items, st):
    return [P(f'• {t}', 'bullet', st) for t in items]


def img_block(name, caption, st):
    path = IMG_DIR / name
    if not path.exists():
        return []
    im = Image(str(path))
    w, h = im.imageWidth, im.imageHeight
    scale = min(1.0, IMG_MAX_W / w, IMG_MAX_H / h)
    im.drawWidth = w * scale
    im.drawHeight = h * scale
    return [Spacer(1, 3), im, P(f'<b>Hình:</b> {caption}', 'caption', st)]


def button_table(rows, st, c1='Nút / ô', c2='Thao tác trong demo'):
    data = [[P(c1, 'cellh', st), P(c2, 'cellh', st)]]
    for a, b in rows:
        data.append([P(a, 'cellb', st), P(b, 'cell', st)])
    t = Table(data, colWidths=[4.3 * cm, 11.3 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HDR),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    return [t, Spacer(1, 7)]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.05 * cm, 'JustPlay Portal — Demo Giao việc cá nhân')
    canvas.drawRightString(A4[0] - 2 * cm, 1.05 * cm, f'Trang {doc.page}')
    canvas.restoreState()


def build():
    register_fonts()
    st = styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
        title='Hướng dẫn Giao việc cá nhân — Demo fleetd-base',
        author='JustPlay Portal',
    )
    story = []

    # --- Bìa ---
    story.append(Spacer(1, 1.4 * cm))
    story.append(P('JUSTPLAY PORTAL', 'title', st))
    story.append(P('Hướng dẫn Công việc: cá nhân · dự án nội bộ · liên phòng ban', 'subtitle', st))
    story.append(P('Từ lúc tạo việc → đến lúc duyệt hoàn thành', 'subtitle', st))
    story.append(P('portal.justplay.vn/cong-viec/ca-nhan/', 'subtitle', st))
    story.append(P(f'Tài liệu: {TODAY.strftime("%d/%m/%Y")}', 'subtitle', st))
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width='100%', thickness=2, color=BRAND))
    story.append(Spacer(1, 0.35 * cm))
    story.append(P(
        '<b>Demo đã chạy trên hệ thống (hoàn thành hôm nay):</b><br/>'
        f'• Việc: <b>setup fleetd-base trên VPS</b><br/>'
        f'• Hạn: 15 ngày → <b>{DUE.strftime("%d/%m/%Y")}</b><br/>'
        f'• Kết quả: <b>Hoàn thành</b> ngày <b>{TODAY.strftime("%d/%m/%Y")}</b>',
        'demo', st,
    ))
    story.extend(bullets([
        'Ba menu: <b>Giao việc cá nhân</b>, <b>Dự án nội bộ</b>, <b>Dự án liên phòng ban</b>.',
        'Hai vai trò: <b>Quản lý</b> (tạo / duyệt) và <b>Nhân viên</b> (nhận / làm / tiếp nhận).',
        'URL: /cong-viec/ca-nhan/ · /cong-viec/du-an/ · /cong-viec/lien-phong-ban/',
    ], st))
    story.append(PageBreak())

    # --- Mục lục ---
    story.append(P('Mục lục', 'h1', st))
    story.extend(bullets([
        'A. Bản đồ tab &amp; trạng thái (việc cá nhân)',
        'B–D. Giao việc cá nhân (quản lý tạo → nhân viên làm → quản lý duyệt)',
        'E. Dự án nội bộ',
        'F. Dự án liên phòng ban',
        'G. Bảng toàn bộ nút theo màn hình',
        'H. Checklist',
    ], st))
    story.append(PageBreak())

    # --- A ---
    story.append(P('A. Bản đồ tab &amp; trạng thái', 'h1', st))
    story.append(P('A.1. Bốn tab dưới tiêu đề «Giao việc cá nhân»', 'h2', st))
    story.extend(button_table([
        ('Việc của tôi', 'Nhân viên dùng — /cong-viec/ca-nhan/cua-toi/'),
        ('Việc đã giao', 'Quản lý theo dõi — /cong-viec/ca-nhan/da-giao/'),
        ('Giao việc', 'Quản lý tạo việc mới — /cong-viec/ca-nhan/giao/'),
        ('Việc lặp', 'Quản lý chu kỳ lặp (không dùng trong demo này)'),
    ], st, 'Tab', 'Ai dùng / URL'))

    story.append(P('A.2. Trạng thái trong demo này', 'h2', st))
    story.extend(button_table([
        ('Chờ xác nhận', 'Sau khi quản lý bấm Giao việc'),
        ('Đang thực hiện', 'Badge trên việc — pill lọc ghi «Đang làm»'),
        ('Chờ duyệt', 'Sau khi nhân viên bấm Nộp chờ duyệt'),
        ('Hoàn thành', 'Sau khi quản lý bấm Duyệt hoàn thành hôm nay'),
        ('Đã hủy / Cần sửa / Từ chối', 'Không dùng trong demo hoàn thành này'),
    ], st, 'Trạng thái', 'Khi nào xuất hiện'))
    story.append(PageBreak())

    # --- B Quản lý tạo ---
    story.append(P('B. Quản lý — tạo việc', 'h1', st))
    story.append(P('Bước 1. Mở Giao việc cá nhân', 'step', st))
    story.extend(bullets([
        'Menu trái: <b>Báo cáo &amp; Công việc</b> → <b>Giao việc cá nhân</b>.',
        'Tab <b>Việc đã giao</b> — URL: /cong-viec/ca-nhan/da-giao/',
        'Bấm tab <b>+ Giao việc</b> để mở form. Tab <b>Việc lặp</b> không dùng trong demo.',
    ], st))
    story.extend(img_block('cong-viec-da-giao.png', 'Việc đã giao — 4 tab + pill trạng thái + ô Tìm', st))
    story.extend(img_block('cong-viec-form.png', 'Form Giao việc (trống)', st))

    story.append(P('Bước 2. Điền form rồi bấm Giao việc', 'step', st))
    story.extend(button_table([
        ('Tiêu đề', 'setup fleetd-base trên VPS'),
        ('Mô tả chi tiết', 'Cài/cấu hình fleetd-base trên VPS; kiểm tra dịch vụ chạy OK'),
        ('Loại việc', 'Chung'),
        ('Ưu tiên', 'Cao'),
        ('Hạn hoàn thành', f'{DUE.strftime("%d/%m/%Y")} (hôm nay + 15 ngày)'),
        ('Hình ảnh / File', 'Tuỳ chọn — đính kèm tài liệu hướng dẫn cài nếu có'),
        ('Người nhận', 'Chọn <b>nhân viên</b> (tìm theo họ tên / mã NS / account)'),
        ('Không cần duyệt hoàn thành', 'KHÔNG tick — để còn bước duyệt'),
        ('Công việc lặp lại', 'KHÔNG tick (demo 1 lần)'),
        ('Nút Giao việc', 'Bấm để tạo việc'),
        ('Nút Hủy', 'Huỷ form, không tạo'),
        ('Chọn tất cả / Bỏ chọn', 'Trong dropdown người nhận (demo chọn 1 người)'),
    ], st))
    story.extend(img_block('cong-viec-form-filled.png', 'Form đã điền + chọn nhân viên nhận việc', st))

    story.append(P('Bước 3. Việc vừa giao — Chờ xác nhận', 'step', st))
    story.extend(bullets([
        'Hệ thống báo xanh «Đã giao 1 công việc» và mở chi tiết việc.',
        f'Badge vàng <b>Chờ xác nhận</b>, hạn {DUE.strftime("%d/%m/%Y")}.',
        'Nút góc phải <b>Việc đã giao</b> quay danh sách. Nút <b>Hủy công việc</b> phía dưới — không bấm trong demo.',
        'Nhật ký ghi mốc «Giao việc».',
    ], st))
    story.extend(img_block('cong-viec-chi-tiet-moi.png', 'Chi tiết việc mới — Chờ xác nhận', st))
    story.extend(bullets([
        'Tab <b>Việc đã giao</b> + ô Tìm «fleetd» + nút <b>Tìm</b> / <b>×</b> + pill trạng thái.',
        f'Dòng việc: ưu tiên Cao, hạn {DUE.strftime("%d/%m/%Y")}, trạng thái Chờ xác nhận, nút <b>Chi tiết</b>.',
    ], st))
    story.extend(img_block('cong-viec-da-giao-cho-xac-nhan.png', 'Việc đã giao sau khi tạo — Chờ xác nhận', st))
    story.append(PageBreak())

    # --- C Nhân viên ---
    story.append(P('C. Nhân viên — nhận &amp; làm việc', 'h1', st))
    story.append(P('Bước 4. Mở Việc của tôi', 'step', st))
    story.extend(bullets([
        'Menu <b>Giao việc cá nhân</b> → tab <b>Việc của tôi</b> (nhân viên không thấy tab Giao việc / Việc lặp).',
        'Banner vàng «Có 1 việc chờ bạn xác nhận». Pill / ô Tìm «fleetd» → nút <b>Chi tiết</b>.',
    ], st))
    story.extend(img_block('cong-viec-cua-toi.png', 'Việc của tôi — banner chờ xác nhận + pill + Tìm + Chi tiết', st))
    story.extend(button_table([
        ('Pill trạng thái', 'Lọc Tất cả / Chờ xác nhận / Đang làm / …'),
        ('Tìm / ×', 'Tìm «fleetd» hoặc xoá tìm'),
        ('Chi tiết', 'Mở việc setup fleetd-base trên VPS'),
    ], st))

    story.append(P('Bước 5. Xác nhận nhận việc', 'step', st))
    story.extend(button_table([
        ('Xác nhận nhận việc', 'Bấm → badge Đang thực hiện (pill lọc: Đang làm)'),
        ('Từ chối', 'Mở form lý do (demo này KHÔNG dùng)'),
        ('Gửi từ chối', 'Chỉ khi đã điền lý do từ chối'),
        ('Việc của tôi', 'Nút góc phải — quay danh sách'),
    ], st))
    story.extend(img_block('cong-viec-xac-nhan.png', 'Khối Xác nhận — Xác nhận nhận việc / Từ chối / Gửi từ chối', st))

    story.append(P('Bước 6. Làm việc — tiến độ &amp; nộp', 'step', st))
    story.extend(button_table([
        ('Hình ảnh / File', 'Chọn ảnh hoặc file log/config nếu có'),
        ('Tải lên', 'Lưu đính kèm vào việc'),
        ('Thanh Tiến độ %', 'Kéo ví dụ 50% rồi 100%'),
        ('Ghi chú tiến độ', 'VD: «Đã SSH VPS, đang cài fleetd-base»'),
        ('Lưu tiến độ', 'Ghi % + ghi chú vào nhật ký'),
        ('Báo cáo kết quả', 'VD: «fleetd-base chạy OK, health check pass»'),
        ('Nộp chờ duyệt', 'Gửi lên quản lý duyệt — trạng thái Chờ duyệt'),
        ('Hoàn thành', 'Chỉ hiện nếu việc Miễn duyệt (demo này không có)'),
    ], st))
    story.extend(img_block('cong-viec-dang-lam.png', 'Sau xác nhận: Tải lên / Lưu tiến độ / Nộp chờ duyệt', st))
    story.extend(img_block('cong-viec-nop.png', 'Đã lưu 50% rồi điền Báo cáo kết quả, sắp bấm Nộp chờ duyệt', st))
    story.append(PageBreak())

    # --- D Duyệt ---
    story.append(P('D. Quản lý — duyệt hoàn thành', 'h1', st))
    story.append(P('Bước 7. Mở việc chờ duyệt', 'step', st))
    story.extend(bullets([
        'Tab <b>Việc đã giao</b> — banner xanh «N việc chờ duyệt».',
        'Pill <b>Chờ duyệt</b> hoặc Tìm «fleetd» → <b>Chi tiết</b>.',
        'Đọc báo cáo kết quả / file của nhân viên; xem cột <b>Nhật ký</b>.',
    ], st))
    story.extend(img_block('cong-viec-da-giao-cho-duyet.png', 'Việc đã giao — pill Chờ duyệt', st))

    story.append(P('Bước 8. Duyệt hoàn thành (demo hôm nay)', 'step', st))
    story.extend(button_table([
        ('Ghi chú duyệt', 'Tuỳ chọn — VD: «fleetd-base OK trên VPS»'),
        ('Duyệt hoàn thành', 'Bấm → trạng thái Hoàn thành (đã làm trong demo)'),
        ('Ghi chú yêu cầu sửa *', 'Bắt buộc nếu trả về'),
        ('Yêu cầu sửa lại', 'Không dùng trong demo hoàn thành'),
        ('Hủy công việc', 'Không dùng — chỉ khi cần huỷ hẳn'),
        ('Việc đã giao', 'Quay danh sách'),
        ('Giao lại', 'Chỉ hiện khi nhân viên đã Từ chối (không áp dụng demo này)'),
    ], st))
    story.extend(img_block('cong-viec-duyet.png', 'Khối Duyệt — Duyệt hoàn thành / Yêu cầu sửa lại / Hủy công việc', st))

    story.append(P('Kết quả demo việc cá nhân', 'step', st))
    story.extend(bullets([
        f'Trên Việc đã giao: việc «setup fleetd-base trên VPS» = <b>Hoàn thành</b>, hạn {DUE.strftime("%d/%m/%Y")}.',
        f'Ngày hoàn thành demo: <b>{TODAY.strftime("%d/%m/%Y")}</b>.',
        'Nhật ký đủ: Giao việc → Xác nhận → Cập nhật tiến độ 50% → Nộp hoàn thành → Duyệt.',
    ], st))
    story.extend(img_block('cong-viec-hoan-thanh.png', 'Chi tiết sau duyệt — badge Hoàn thành + nhật ký 5 mốc', st))
    story.extend(img_block('cong-viec-da-giao-xong.png', 'Việc đã giao — dòng fleetd-base trạng thái Hoàn thành', st))
    story.append(PageBreak())

    # --- E Dự án nội bộ ---
    story.append(P('E. Dự án nội bộ', 'h1', st))
    story.append(P(
        'Menu <b>Báo cáo &amp; Công việc</b> → <b>Dự án nội bộ</b> '
        '(/cong-viec/du-an/). Nhiều bước trong nhóm; bước có thể chạy song song. '
        'Trạng thái dự án: Nháp · Đang chạy · Hoàn thành · Đã hủy.',
        'body', st,
    ))

    story.append(P('Bước 9. Nhân viên — danh sách dự án', 'step', st))
    story.extend(bullets([
        'Chỉ tab <b>Danh sách dự án</b> (không có + Tạo dự án).',
        'Ô tìm tên dự án / chủ dự án → <b>Tìm</b>. Có dự án thì bấm <b>Chi tiết</b>.',
    ], st))
    story.extend(img_block('cong-viec-du-an-nv.png', 'Dự án nội bộ — góc nhân viên', st))

    story.append(P('Bước 10. Nhân viên — làm một bước', 'step', st))
    story.extend(button_table([
        ('Chi tiết', 'Mở bước mình phụ trách'),
        ('Về dự án', 'Quay trang dự án'),
        ('Xác nhận nhận việc / Từ chối / Gửi từ chối', 'Khi Chờ xác nhận'),
        ('Tải lên / Lưu tiến độ / Nộp chờ duyệt', 'Khi Đang thực hiện / Cần sửa'),
        ('Chuyển giao bước', 'Gửi chủ dự án duyệt chuyển người'),
        ('Gửi yêu cầu / Hủy', 'Trên form chuyển giao'),
    ], st))
    story.extend(bullets([
        'Trạng thái thêm: <b>Chờ bước trước</b> (phụ thuộc), <b>Đã chuyển giao</b>.',
    ], st))

    story.append(P('Bước 11–13. Quản lý — tạo, thêm bước, điều phối', 'step', st))
    story.extend(button_table([
        ('Danh sách dự án / + Tạo dự án', 'Tab trên cùng'),
        ('Tạo dự án đầu tiên', 'Link khi danh sách trống'),
        ('Tên dự án / Mô tả / Hạn dự án / Thành viên', 'Form tạo'),
        ('Lưu dự án / Hủy', 'Gửi hoặc thoát form'),
        ('Hoàn thành dự án', 'Chủ dự án, khi Đang chạy (có xác nhận)'),
        ('Thêm bước', 'Tên bước, ưu tiên, mô tả, người phụ trách, phụ thuộc, hạn'),
        ('Chi tiết / Giao người khác', 'Giao người khác chỉ khi bước Đã từ chối'),
        ('Gửi comment', 'Báo cáo chung — gõ @ để nhắc thành viên'),
        ('Duyệt / Từ chối', 'Khối Chuyển giao chờ duyệt'),
        ('Duyệt hoàn thành / Yêu cầu sửa lại', 'Khi duyệt bước như việc cá nhân'),
    ], st))
    story.extend(img_block('cong-viec-du-an-list.png', 'Danh sách dự án nội bộ — quản lý', st))
    story.extend(img_block('cong-viec-du-an-tao.png', 'Form Tạo dự án nội bộ', st))
    story.append(PageBreak())

    # --- F Liên phòng ban ---
    story.append(P('F. Dự án liên phòng ban', 'h1', st))
    story.append(P(
        'Menu <b>Dự án liên phòng ban</b> (/cong-viec/lien-phong-ban/). '
        'Điều phối nhiều phòng. Tạo dự án cần ≥ 2 phòng ban. '
        'Tab <b>+ Tạo dự án</b> chỉ hiện Giám đốc / Trưởng phòng đủ quyền.',
        'body', st,
    ))

    story.append(P('Bước 14–15. Nhân viên — danh sách &amp; chờ tiếp nhận', 'step', st))
    story.extend(button_table([
        ('Danh sách dự án', 'Xem dự án mình liên quan'),
        ('Chờ tiếp nhận', 'Bước hàng đợi của phòng mình'),
        ('Tìm / Chi tiết', 'Lọc tên, điều phối viên, phòng ban'),
        ('Tiếp nhận', 'Mở form xác nhận nhận bước'),
        ('Xác nhận tiếp nhận / Quay lại', 'Chốt nhận hoặc thoát'),
    ], st))
    story.extend(img_block('cong-viec-lpb-nv.png', 'Danh sách liên phòng ban — nhân viên (không có Tạo dự án)', st))
    story.extend(img_block('cong-viec-lpb-cho-nv.png', 'Chờ phòng tiếp nhận', st))

    story.append(P('Bước 16–18. Quản lý — tạo &amp; thêm bước', 'step', st))
    story.extend(button_table([
        ('Danh sách / Chờ tiếp nhận / + Tạo dự án', 'Ba tab điều phối'),
        ('Tên / Mô tả / Hạn / Phòng ban tham gia', 'Form tạo — chọn ≥ 2 phòng'),
        ('Lưu dự án / Hủy', 'Gửi hoặc thoát'),
        ('Hoàn thành dự án', 'Khi Đang chạy'),
        ('Thêm bước', 'Phòng ban xử lý + Cách gán: Hàng đợi phòng ban hoặc Chỉ định người'),
        ('Tiếp nhận / Chi tiết / Giao người khác', 'Trên bảng bước'),
        ('Gửi comment', 'Điều phối gửi được; Trưởng BP chỉ đọc thì không'),
    ], st))
    story.extend(img_block('cong-viec-lpb-list.png', 'Danh sách dự án liên phòng ban — quản lý', st))
    story.extend(img_block('cong-viec-lpb-tao.png', 'Form Tạo dự án liên phòng ban', st))
    story.extend(img_block('cong-viec-lpb-cho.png', 'Tab Chờ tiếp nhận — quản lý', st))
    story.append(PageBreak())

    # --- G bảng nút ---
    story.append(P('G. Bảng toàn bộ nút theo màn hình', 'h1', st))
    story.append(P('G.1. Việc của tôi (nhân viên)', 'h2', st))
    story.extend(button_table([
        ('Pill lọc', 'Lọc theo trạng thái'),
        ('Tìm / ×', 'Tìm kiếm / xoá tìm'),
        ('Chi tiết', 'Mở việc'),
    ], st))
    story.append(P('G.2. Việc đã giao (quản lý)', 'h2', st))
    story.extend(button_table([
        ('Banner chờ duyệt / từ chối', 'Cảnh báo số việc cần xử lý'),
        ('Pill / Tìm / ×', 'Lọc &amp; tìm người nhận / tiêu đề'),
        ('Chi tiết', 'Xem / duyệt / huỷ'),
        ('Đổi người nhận / Giao lại', 'Đổi người khi Chờ xác nhận; Giao lại khi Từ chối'),
    ], st))
    story.append(P('G.3. Form Giao việc', 'h2', st))
    story.extend(button_table([
        ('Giao việc', 'Tạo việc (disabled nếu không có người nhận)'),
        ('Hủy', 'Về /cong-viec/ca-nhan/da-giao/'),
    ], st))
    story.append(P('G.4. Chi tiết việc / bước', 'h2', st))
    story.extend(button_table([
        ('Xác nhận nhận việc / Từ chối / Gửi từ chối', 'Phía nhân viên khi Chờ xác nhận'),
        ('Tải lên / Lưu tiến độ / Nộp chờ duyệt', 'Phía nhân viên khi Đang làm / Cần sửa'),
        ('Tải thêm', 'Nhân viên khi Chờ duyệt — bổ sung file'),
        ('Duyệt hoàn thành / Yêu cầu sửa lại / Hủy', 'Phía quản lý'),
        ('Về dự án / Chuyển giao bước / Tiếp nhận bước', 'Khi bước thuộc dự án'),
    ], st))
    story.append(P('G.5. Dự án nội bộ &amp; liên phòng ban', 'h2', st))
    story.extend(button_table([
        ('+ Tạo dự án / Lưu dự án / Hủy', 'Quản lý tạo'),
        ('Thêm bước / Hoàn thành dự án', 'Chi tiết dự án'),
        ('Gửi comment / Duyệt / Từ chối chuyển giao', 'Điều phối'),
        ('Chờ tiếp nhận / Tiếp nhận / Xác nhận tiếp nhận', 'Liên phòng ban'),
    ], st))
    story.append(PageBreak())

    # --- H checklist ---
    story.append(P('H. Checklist', 'h1', st))
    story.extend(bullets([
        f'[ ] Quản lý: Giao việc → tiêu đề fleetd-base → hạn {DUE.strftime("%d/%m/%Y")} → chọn nhân viên → Giao việc',
        '[ ] Việc đã giao hiện Chờ xác nhận',
        '[ ] Nhân viên: Việc của tôi → Chi tiết → Xác nhận nhận việc',
        '[ ] Nhân viên: Lưu tiến độ → (tuỳ chọn) Tải lên → Nộp chờ duyệt',
        '[ ] Quản lý: Việc đã giao → Chi tiết → Duyệt hoàn thành',
        f'[ ] Việc cá nhân Hoàn thành ngày {TODAY.strftime("%d/%m/%Y")}',
        '[ ] Dự án nội bộ: Tạo dự án → Thêm bước → nhân viên làm bước → duyệt → Hoàn thành dự án',
        '[ ] Liên phòng ban: Tạo (≥2 phòng) → Thêm bước hàng đợi → Chờ tiếp nhận → Xác nhận tiếp nhận',
    ], st))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(P(
        'Nguồn: UI module tasks · portal.justplay.vn/cong-viec/',
        'caption', st,
    ))
    story.append(P('© JustPlay.vn — Portal nội bộ · Design by IT', 'caption', st))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f'Da tao: {OUTPUT}')
    return OUTPUT


if __name__ == '__main__':
    build()
