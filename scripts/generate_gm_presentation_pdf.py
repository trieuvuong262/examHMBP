#!/usr/bin/env python3
"""Xuất PDF tài liệu trình bày JustPlay Portal cho Giám đốc."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs' / 'JustPlay_Portal_Trinh_Bay_Giam_Doc.pdf'

FONT_REG = 'JPBody'
FONT_BOLD = 'JPBodyBold'


def _register_fonts():
    candidates = [
        (Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf', 'arialbd.ttf'),
        (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), 'DejaVuSans-Bold.ttf'),
    ]
    for reg_path, bold_name in candidates:
        bold_path = reg_path.parent / bold_name
        if reg_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont(FONT_REG, str(reg_path)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
            return
    raise SystemExit('Không tìm thấy font hỗ trợ tiếng Việt (Arial/DejaVu).')


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'Title', fontName=FONT_BOLD, fontSize=22, leading=28,
            textColor=colors.HexColor('#dc2626'), alignment=TA_CENTER, spaceAfter=6,
        ),
        'subtitle': ParagraphStyle(
            'Subtitle', fontName=FONT_REG, fontSize=11, leading=14,
            textColor=colors.HexColor('#64748b'), alignment=TA_CENTER, spaceAfter=20,
        ),
        'h1': ParagraphStyle(
            'H1', fontName=FONT_BOLD, fontSize=14, leading=18,
            textColor=colors.HexColor('#dc2626'), spaceBefore=14, spaceAfter=8,
        ),
        'h2': ParagraphStyle(
            'H2', fontName=FONT_BOLD, fontSize=11.5, leading=15,
            textColor=colors.HexColor('#1e293b'), spaceBefore=10, spaceAfter=6,
        ),
        'body': ParagraphStyle(
            'Body', fontName=FONT_REG, fontSize=10, leading=14,
            textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        'bullet': ParagraphStyle(
            'Bullet', fontName=FONT_REG, fontSize=10, leading=14,
            textColor=colors.HexColor('#334155'), leftIndent=14, spaceAfter=4,
        ),
        'quote': ParagraphStyle(
            'Quote', fontName=FONT_REG, fontSize=10, leading=14,
            textColor=colors.HexColor('#1e293b'), leftIndent=12, rightIndent=12,
            backColor=colors.HexColor('#fef2f2'), borderPadding=10, spaceAfter=10,
        ),
        'footer': ParagraphStyle(
            'Footer', fontName=FONT_REG, fontSize=8, textColor=colors.grey,
        ),
    }


def _table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REG),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


def build_pdf():
    _register_fonts()
    st = _styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title='JustPlay Portal - Trình bày Giám đốc',
        author='JustPlay IT Team',
    )
    story = []

    # Cover
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph('JUSTPLAY PORTAL', st['title']))
    story.append(Paragraph('Tài liệu trình bày Ban Giám đốc', st['subtitle']))
    story.append(Paragraph(
        f'Cổng thông tin nội bộ · portal.justplay.vn<br/>'
        f'Ngày xuất bản: {date.today().strftime("%d/%m/%Y")}',
        st['subtitle'],
    ))
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#dc2626')))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        'JustPlay Portal là hệ thống quản trị nhân sự và vận hành số tích hợp trên một nền tảng duy nhất, '
        'phục vụ nhân viên xưởng (mobile), tổ trưởng, giám đốc và phòng nhân sự.',
        st['body'],
    ))
    story.append(PageBreak())

    # 1. Overview
    story.append(Paragraph('1. Tổng quan hệ thống', st['h1']))
    story.append(Paragraph(
        'Portal gom sáu luồng vận hành chính vào một cổng thông tin, thay thế dần Excel, Zalo và giấy tờ rời rạc.',
        st['body'],
    ))
    story.append(_table([
        ['#', 'Module', 'Giá trị'],
        ['1', 'Thông báo', 'Chính sách, quy định — có xác nhận đã đọc'],
        ['2', 'Báo cáo công việc', 'Sản lượng theo ca/công đoạn, HOD giám sát real-time'],
        ['3', 'KPI', 'Đánh giá hiệu suất năm: NV → HOD → GM'],
        ['4', 'Đào tạo E-Learning', 'Khóa học video/PDF, theo dõi tiến độ'],
        ['5', 'Kiểm tra năng lực', 'Bài thi trắc nghiệm + tự luận'],
        ['6', 'Tuyển dụng + Nhân sự', 'Pipeline ứng viên → tạo tài khoản nhân viên'],
    ], col_widths=[1 * cm, 4.5 * cm, 10 * cm]))

    # 2. Roles
    story.append(Paragraph('2. Phân quyền bốn cấp', st['h1']))
    story.append(_table([
        ['Vai trò', 'Đối tượng', 'Quyền chính'],
        ['Nhân viên', 'Công nhân may, QC, kho…', 'Đọc TB, nộp báo cáo, học, thi, tự chấm KPI'],
        ['HOD', 'Tổ trưởng, trưởng BP', 'Xem báo cáo team, chấm KPI cấp dưới, giao KPI'],
        ['GM', 'Giám đốc', 'Xem toàn công ty, chốt KPI, quyết định cuối'],
        ['HR / IT', 'Phòng nhân sự', 'Quản lý TK, tuyển dụng, đào tạo, thi, thông báo'],
    ], col_widths=[2.5 * cm, 4 * cm, 9 * cm]))
    story.append(Paragraph(
        'Nguyên tắc: mỗi người chỉ thấy đúng phạm vi — nhân viên không vào khu quản trị; '
        'HOD chỉ thấy team mình; GM và HR thấy toàn bộ.',
        st['body'],
    ))

    # 3. Modules detail
    story.append(PageBreak())
    story.append(Paragraph('3. Chi tiết chức năng', st['h1']))

    sections = [
        ('3.1 Trang chủ — Việc cần làm hôm nay', [
            'Hệ thống tự nhắc việc theo vai trò sau khi đăng nhập:',
            '• Thông báo chưa đọc',
            '• Báo cáo hôm nay chưa nộp / còn nháp',
            '• KPI kỳ hiện tại chưa hoàn tất',
            '• (HOD/GM) Nhân viên chưa nộp báo cáo',
            '• (HOD/GM) KPI cấp dưới chờ chấm / chờ chốt',
            '• Bài thi đang mở chưa làm',
            '→ Giám đốc mở portal là thấy ngay tình hình, không cần nhắc thủ công.',
        ]),
        ('3.2 Thông báo nội bộ', [
            'HR tạo thông báo dạng văn bản, PDF hoặc video; có thể ghim tin quan trọng.',
            'Nhân viên đọc và xác nhận đã đọc — hệ thống đếm ai chưa đọc.',
            'Lợi ích: chính sách, ATLD, thay đổi quy trình có bằng chứng phổ biến.',
        ]),
        ('3.3 Báo cáo công việc hàng ngày', [
            'Nhân viên (mobile): nhập sản lượng theo ca, công đoạn (Cắt, May, QC, Kho…), mã đơn, sản phẩm.',
            'Có chức năng sao chép báo cáo hôm qua để nhập nhanh.',
            'HOD: xem báo cáo team theo ngày — ai đã nộp, ai chưa; ghi chú phản hồi.',
            'GM / HR: xem báo cáo toàn công ty.',
        ]),
        ('3.4 KPI — Đánh giá hiệu suất năm', [
            '4 trụ cột: Nguồn nhân lực, Tài chính, Khách hàng, Vận hành.',
            'Đánh giá theo quý (Q1–Q4), bán niên hoặc cả năm.',
            'Luồng 3 bước: Nhân viên tự chấm → HOD chấm → GM chốt.',
            'HR/Admin mở/đóng từng kỳ; import Excel giao KPI hàng loạt.',
        ]),
        ('3.5 Đào tạo E-Learning', [
            'Khóa học theo danh mục: chương → bài (video, PDF, bài đọc).',
            'Gán khóa theo chức danh/vai trò; theo dõi % hoàn thành.',
            'Có thể gắn bài thi cuối khóa.',
        ]),
        ('3.6 Kiểm tra năng lực', [
            'Ngân hàng câu hỏi → đề thi → gán thí sinh, giới hạn thời gian.',
            'Trắc nghiệm chấm tự động; tự luận HR chấm tay.',
        ]),
        ('3.7 Tuyển dụng → Onboarding', [
            'Kanban: Mới nộp → Xem xét → Phỏng vấn → Trúng tuyển.',
            'Lưu CV, lịch phỏng vấn, ghi chú HR, chứng chỉ hành nghề (CCHN).',
            'Ứng viên trúng tuyển → tạo tài khoản nhân viên tự động (@justplay.vn).',
        ]),
        ('3.8 Quản lý nhân sự', [
            'Danh sách nhân viên: họ tên, chức danh, vai trò (NV/HOD/GM).',
            'HOD được gán danh sách cấp dưới.',
            'Import/Export Excel, reset mật khẩu, tải file mẫu.',
        ]),
    ]
    for title, lines in sections:
        story.append(Paragraph(title, st['h2']))
        for line in lines:
            style = st['bullet'] if line.startswith('•') or line.startswith('→') else st['body']
            story.append(Paragraph(line, style))

    # 4. UX & Infra
    story.append(PageBreak())
    story.append(Paragraph('4. Trải nghiệm người dùng', st['h1']))
    story.append(_table([
        ['Đối tượng', 'Thiết bị', 'Điểm nổi bật'],
        ['Công nhân xưởng', 'Điện thoại', 'Menu dưới: Trang chủ · TB · Báo cáo · KPI · Học'],
        ['Tổ trưởng', 'Mobile + PC', 'Báo cáo team, chấm KPI cấp dưới'],
        ['Giám đốc', 'PC', 'KPI toàn công ty, chốt điểm, dashboard'],
        ['HR', 'PC', 'Tuyển dụng, đào tạo, thi, nhân sự, thông báo'],
    ], col_widths=[3.5 * cm, 3 * cm, 9 * cm]))

    story.append(Paragraph('5. Hạ tầng triển khai', st['h1']))
    story.append(_table([
        ['Hạng mục', 'Chi tiết'],
        ['Domain', 'portal.justplay.vn'],
        ['Máy chủ', 'VPS Docker (PostgreSQL + Gunicorn + Nginx)'],
        ['HTTPS', "Let's Encrypt (SSL có thể bật)"],
        ['Deploy', 'Script deploy.sh — pull, migrate, collectstatic'],
        ['Bảo mật', 'Khóa TK khi đăng nhập sai; bắt đổi MK lần đầu'],
    ], col_widths=[4 * cm, 11.5 * cm]))

    story.append(Paragraph('6. Thông điệp trình bày (30 giây)', st['h1']))
    story.append(Paragraph(
        '<i>“JustPlay Portal là cổng số nội bộ — nhân viên xưởng báo cáo sản lượng và học tập trên điện thoại; '
        'tổ trưởng giám sát team và chấm KPI; Giám đốc chốt hiệu suất toàn công ty; HR quản lý tuyển dụng, '
        'đào tạo và nhân sự trên cùng một nền tảng. Hệ thống đã triển khai tại portal.justplay.vn, '
        'mobile-friendly, phân quyền rõ ràng.”</i>',
        st['quote'],
    ))

    story.append(Paragraph('7. Gợi ý demo live (10–15 phút)', st['h1']))
    demo_steps = [
        '1. Đăng nhập portal.justplay.vn',
        '2. Trang chủ — widget việc cần làm + lối tắt',
        '3. Báo cáo hôm nay (mobile)',
        '4. Báo cáo team (HOD)',
        '5. KPI — ma trận chấm điểm',
        '6. Thông báo — xác nhận đã đọc',
        '7. Khóa học + Bài thi',
        '8. Kanban tuyển dụng → Tạo user',
        '9. Quản lý nhân sự — import Excel',
    ]
    for step in demo_steps:
        story.append(Paragraph(step, st['bullet']))

    story.append(Paragraph('8. Chỉ số báo cáo định kỳ cho GM', st['h1']))
    kpis = [
        '• % nhân viên nộp báo cáo đúng hạn / ngày',
        '• % thông báo đã được xác nhận đọc',
        '• Tiến độ KPI theo kỳ (đã chốt / chưa chốt)',
        '• Số khóa học hoàn thành / đang học',
        '• Pipeline tuyển dụng (ứng viên theo giai đoạn)',
    ]
    for k in kpis:
        story.append(Paragraph(k, st['bullet']))

    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(Paragraph('© JustPlay.vn · JustPlay IT Team · Tài liệu nội bộ', st['footer']))

    doc.build(story)
    print(f'Created: {OUTPUT}')


if __name__ == '__main__':
    build_pdf()
