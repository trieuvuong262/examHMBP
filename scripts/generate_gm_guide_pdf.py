#!/usr/bin/env python3
"""
Xuat PDF cam nang JustPlay Portal cho Giam doc tu doc.
Kieu huong dan: chi tiet, nhieu hinh anh tu portal.justplay.vn

Truoc khi chay:
  python scripts/capture_gm_guide_screenshots.py
  python scripts/generate_gm_guide_pdf.py
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / 'docs' / 'images' / 'gm-guide'
OUTPUT = ROOT / 'docs' / 'JustPlay_Portal_Cam_Nang_Giam_Doc.pdf'

FONT = 'JPBody'
FONT_BOLD = 'JPBodyBold'
PAGE_W = A4[0] - 4 * cm
IMG_MAX_W = 15.5 * cm
IMG_MAX_H = 16 * cm


def register_fonts():
    win = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    reg, bold = win / 'arial.ttf', win / 'arialbd.ttf'
    if not reg.exists():
        reg = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        bold = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont(FONT, str(reg)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))


def S():
    return {
        'title': ParagraphStyle('t', fontName=FONT_BOLD, fontSize=24, leading=30,
                                textColor=colors.HexColor('#dc2626'), alignment=TA_CENTER, spaceAfter=8),
        'subtitle': ParagraphStyle('st', fontName=FONT, fontSize=11, leading=14,
                                   textColor=colors.HexColor('#64748b'), alignment=TA_CENTER, spaceAfter=6),
        'h1': ParagraphStyle('h1', fontName=FONT_BOLD, fontSize=16, leading=20,
                             textColor=colors.HexColor('#dc2626'), spaceBefore=16, spaceAfter=8),
        'h2': ParagraphStyle('h2', fontName=FONT_BOLD, fontSize=12, leading=16,
                             textColor=colors.HexColor('#1e293b'), spaceBefore=10, spaceAfter=5),
        'body': ParagraphStyle('b', fontName=FONT, fontSize=10.5, leading=15,
                               textColor=colors.HexColor('#334155'), alignment=TA_JUSTIFY, spaceAfter=6),
        'bullet': ParagraphStyle('bu', fontName=FONT, fontSize=10.5, leading=15,
                                 textColor=colors.HexColor('#334155'), leftIndent=14, spaceAfter=4),
        'step': ParagraphStyle('step', fontName=FONT_BOLD, fontSize=10.5, leading=15,
                               textColor=colors.HexColor('#b91c1c'), leftIndent=0, spaceBefore=6, spaceAfter=3),
        'caption': ParagraphStyle('cap', fontName=FONT, fontSize=9, leading=12,
                                  textColor=colors.HexColor('#64748b'), alignment=TA_CENTER, spaceAfter=10),
        'tip': ParagraphStyle('tip', fontName=FONT, fontSize=10, leading=14,
                              textColor=colors.HexColor('#1e40af'), backColor=colors.HexColor('#eff6ff'),
                              borderPadding=8, leftIndent=6, rightIndent=6, spaceAfter=8),
        'footer': ParagraphStyle('f', fontName=FONT, fontSize=8, textColor=colors.grey),
    }


def P(text, style_key, styles):
    return Paragraph(text.replace('\n', '<br/>'), styles[style_key])


def img(name: str, caption: str, styles, mobile=False):
    path = IMG_DIR / name
    if not path.exists():
        return [P(f'<i>(Chua co anh: {name})</i>', 'caption', styles)]
    im = Image(str(path))
    w, h = im.imageWidth, im.imageHeight
    max_w = 8 * cm if mobile else IMG_MAX_W
    max_h = 14 * cm if mobile else IMG_MAX_H
    scale = min(1.0, max_w / w, max_h / h)
    im.drawWidth = w * scale
    im.drawHeight = h * scale
    return [Spacer(1, 6), im, P(f'<b>Hinh:</b> {caption}', 'caption', styles)]


def bullets(items, styles):
    return [P(f'• {t}', 'bullet', styles) for t in items]


def steps(items, styles):
    out = []
    for i, (title, desc) in enumerate(items, 1):
        out.append(P(f'Bước {i}. {title}', 'step', styles))
        out.append(P(desc, 'body', styles))
    return out


def build():
    register_fonts()
    st = S()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title='JustPlay Portal - Cam nang Giam doc',
    )
    story = []

    # === BIA ===
    story.append(Spacer(1, 1.5 * cm))
    story.append(P('JUSTPLAY PORTAL', 'title', st))
    story.append(P('Cẩm nang hệ thống dành cho Ban Giám đốc', 'subtitle', st))
    story.append(P('portal.justplay.vn', 'subtitle', st))
    story.append(P(f'Phiên bản tài liệu: {date.today().strftime("%d/%m/%Y")}', 'subtitle', st))
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#dc2626')))
    story.append(Spacer(1, 0.5 * cm))
    story.extend(bullets([
        'Tài liệu này mô tả đầy đủ các chức năng JustPlay Portal — bạn có thể đọc theo thứ tự hoặc nhảy tới mục cần.',
        'Mỗi mục có ảnh chụp màn hình thực tế từ hệ thống đang vận hành.',
        'Không cần trình bày miệng — đọc và tham chiếu khi cần.',
    ], st))
    story.append(PageBreak())

    # === MUC LUC ===
    story.append(P('Mục lục', 'h1', st))
    toc = [
        '0. Giới thiệu chung',
        '1. Truy cập và đăng nhập',
        '2. Trang chủ và menu hệ thống',
        '3. Thông báo nội bộ',
        '4. Báo cáo công việc hàng ngày',
        '5. Đánh giá KPI',
        '6. Đào tạo E-Learning',
        '7. Kiểm tra năng lực',
        '8. Quản trị: Dashboard, Nhân sự, Tuyển dụng, Đào tạo',
        '9. Phân quyền trong tổ chức',
        '10. Hướng dẫn sử dụng trên portal',
        '11. Hạ tầng và bảo mật',
    ]
    story.extend(bullets(toc, st))
    story.append(PageBreak())

    # === 0. GIOI THIEU ===
    story.append(P('0. Giới thiệu chung', 'h1', st))
    story.append(P(
        'JustPlay Portal là cổng thông tin nội bộ của JustPlay.vn, tích hợp sáu nhóm chức năng '
        'trên một nền tảng duy nhất. Hệ thống thay thế dần Excel, Zalo và giấy tờ rời rạc bằng quy trình '
        'số có phân quyền, theo dõi được và dùng tốt trên điện thoại.',
        'body', st))
    story.append(P('Sáu module chính', 'h2', st))
    t = Table([
        ['Module', 'Mục đích', 'Ai dùng nhiều nhất'],
        ['Thông báo', 'Phổ biến chính sách, quy định; xác nhận đã đọc', 'HR tạo · Mọi người đọc'],
        ['Báo cáo', 'Sản lượng theo ca, công đoạn, mã đơn hàng', 'NV xưởng nộp · HOD/GM xem team'],
        ['KPI', 'Đánh giá hiệu suất năm, chấm theo quý', 'NV tự chấm · HOD chấm · GM chốt'],
        ['Đào tạo', 'Khóa học video/PDF, theo dõi tiến độ', 'NV học · HR quản lý khóa'],
        ['Kiểm tra', 'Bài thi trắc nghiệm và tự luận', 'NV thi · HR ra đề và chấm'],
        ['Tuyển dụng', 'Pipeline ứng viên → tạo tài khoản nhân viên', 'HR / quản trị'],
    ], colWidths=[2.8 * cm, 6.5 * cm, 5.2 * cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD), ('FONTNAME', (0, 1), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(P(
        'Giám đốc sử dụng portal chủ yếu để: xem tổng quan việc cần làm, theo dõi báo cáo toàn công ty, '
        'chốt điểm KPI cấp cuối, và (khi có quyền quản trị) giám sát tuyển dụng — đào tạo — nhân sự.',
        'body', st))

    # === 1. DANG NHAP ===
    story.append(PageBreak())
    story.append(P('1. Truy cập và đăng nhập', 'h1', st))
    story.extend(steps([
        ('Mở trình duyệt', 'Truy cập địa chỉ <b>https://portal.justplay.vn</b> trên máy tính hoặc điện thoại.'),
        ('Nhập tài khoản', 'Dùng <b>Tên đăng nhập</b> và <b>Mật khẩu</b> do HR cấp. Có thể đăng nhập bằng email dạng ten.ho@justplay.vn.'),
        ('Bấm Đăng nhập', 'Nút đỏ <b>Đăng nhập</b> ở cuối form. Nếu sai quá nhiều lần, tài khoản sẽ bị khóa tạm thời.'),
        ('Đổi mật khẩu lần đầu', 'Lần đăng nhập đầu tiên hệ thống có thể bắt buộc đổi mật khẩu — nên thực hiện ngay.'),
    ], st))
    story.extend(img('01-dang-nhap.png', 'Màn hình đăng nhập JustPlay Portal (máy tính).', st))
    story.extend(img('01-dang-nhap-mobile.png', 'Màn hình đăng nhập trên điện thoại.', st, mobile=True))
    story.extend(img('04-doi-mat-khau.png', 'Màn hình đổi mật khẩu sau khi đăng nhập.', st))

    # === 2. TRANG CHU ===
    story.append(PageBreak())
    story.append(P('2. Trang chủ và menu hệ thống', 'h1', st))
    story.append(P(
        'Sau đăng nhập, trang chủ hiển thị lời chào và khu vực <b>Việc cần làm hôm nay</b> — '
        'hệ thống tự liệt kê thông báo chưa đọc, báo cáo chưa nộp, KPI đang mở, bài thi chưa làm, '
        'và (với HOD/GM) số nhân viên chưa nộp báo cáo hoặc KPI chờ duyệt.',
        'body', st))
    story.append(P('Thanh menu trên (desktop)', 'h2', st))
    story.extend(bullets([
        'Thông Báo · KPI · Báo Cáo · Hướng dẫn',
        'Quản trị viên (HR) còn thấy: Tuyển dụng · Đào tạo · Kiểm tra · Nhân sự',
    ], st))
    story.append(P('Trên điện thoại', 'h2', st))
    story.extend(bullets([
        'Biểu tượng ☰ góc trái — mở menu trượt đầy đủ các mục',
        'Thanh menu dưới cùng: Trang chủ · Thông báo · Báo cáo · KPI · Học — truy cập nhanh khi đứng xưởng',
    ], st))
    story.extend(img('02-trang-chu.png', 'Trang chủ portal — widget việc cần làm và lối tắt các module.', st))
    story.extend(img('02-trang-chu-mobile.png', 'Trang chủ trên điện thoại — thanh menu dưới cùng.', st, mobile=True))
    story.extend(img('03-menu-mobile.png', 'Menu trượt trên mobile khi bấm biểu tượng ☰.', st, mobile=True))

    # === 3. THONG BAO ===
    story.append(PageBreak())
    story.append(P('3. Thông báo nội bộ', 'h1', st))
    story.append(P(
        'Module thông báo dùng để HR/Ban quản lý phổ biến chính sách, quy định, thay đổi quy trình. '
        'Nội dung có thể là văn bản soạn trực tiếp, file PDF hoặc video.',
        'body', st))
    story.extend(steps([
        ('Vào mục Thông Báo', 'Từ menu trên hoặc thẻ Trang chủ / thông báo trên mobile.'),
        ('Đọc danh sách', 'Thông báo ghim hiển thị đầu; badge vàng = chưa đọc, xanh = đã đọc.'),
        ('Xem chi tiết', 'Bấm <b>Xem chi tiết</b> để mở nội dung đầy đủ.'),
        ('Xác nhận đã đọc', 'Bấm nút xác nhận — HR theo dõi được ai chưa đọc.'),
    ], st))
    story.extend(img('05-thong-bao.png', 'Danh sách thông báo nội bộ.', st))
    story.extend(img('05-thong-bao-mobile.png', 'Thông báo trên điện thoại.', st, mobile=True))
    story.append(P(
        'Với vai trò quản trị, HR có thể tạo/sửa thông báo, ghim tin quan trọng, bật/tắt hiển thị '
        'và xem thống kê số lượt đọc.',
        'tip', st))

    # === 4. BAO CAO ===
    story.append(PageBreak())
    story.append(P('4. Báo cáo công việc hàng ngày', 'h1', st))
    story.append(P(
        'Đây là module cốt lõi cho sản xuất: mỗi nhân viên nộp báo cáo theo <b>ngày</b> và <b>ca</b> '
        '(sáng/chiều/đêm). Mỗi dòng báo cáo ghi công đoạn (Cắt, May, QC, Kho…), mã đơn/style, sản phẩm và số lượng.',
        'body', st))
    story.append(P('4.1 Nhân viên nộp báo cáo', 'h2', st))
    story.extend(steps([
        ('Vào Báo cáo hôm nay', 'Menu Báo Cáo hoặc widget trang chủ.'),
        ('Thêm dòng', 'Mỗi dòng = một công đoạn / đơn hàng. Nhập số lượng thực tế.'),
        ('Sao chép hôm qua', 'Nút <b>Sao chép HQ</b> copy toàn bộ dòng từ ngày hôm trước — tiết kiệm thời gian.'),
        ('Nộp báo cáo', 'Lưu nháp hoặc nộp chính thức. Sau khi nộp vẫn có thể sửa và nộp lại.'),
    ], st))
    story.extend(img('06-bao-cao-hom-nay.png', 'Form nhập báo cáo công việc hôm nay.', st))
    story.extend(img('06-bao-cao-hom-nay-mobile.png', 'Nhập báo cáo trên điện thoại tại xưởng.', st, mobile=True))
    story.extend(img('06-bao-cao-lich-su.png', 'Lịch sử báo cáo cá nhân 30 ngày gần nhất.', st))
    story.append(P('4.2 Tổ trưởng / Giám đốc xem team', 'h2', st))
    story.extend(steps([
        ('Vào Báo cáo team', 'Menu hoặc widget “Báo cáo team” trên trang chủ.'),
        ('Chọn ngày', 'Xem danh sách nhân viên: ai đã nộp, ai chưa, trạng thái nháp/đã nộp.'),
        ('Xem chi tiết', 'Mở từng báo cáo, ghi chú phản hồi và đánh dấu đã xem.'),
    ], st))
    story.extend(img('06-bao-cao-team.png', 'Trang báo cáo team — Giám đốc/HOD theo dõi toàn bộ hoặc cấp dưới.', st))
    story.append(P(
        'Giám đốc và HR (staff) xem được báo cáo <b>toàn công ty</b>. '
        'HOD chỉ xem nhân viên thuộc danh sách cấp dưới được HR gán.',
        'tip', st))

    # === 5. KPI ===
    story.append(PageBreak())
    story.append(P('5. Đánh giá KPI', 'h1', st))
    story.append(P(
        'KPI năm được giao theo mô hình <b>top-down</b>: HOD/GM giao chỉ tiêu, nhân viên không tự tạo bảng KPI. '
        'Chỉ tiêu chia theo bốn trụ cột: Nguồn nhân lực, Tài chính, Khách hàng, Vận hành — Công nghệ.',
        'body', st))
    story.append(P('Luồng chấm điểm ba cấp', 'h2', st))
    story.extend(bullets([
        '<b>Bước 1 — Nhân viên:</b> tự chấm điểm khi kỳ đang mở (Q1, Q2, Q3, Q4 hoặc bán niên/cả năm), rồi gửi lên.',
        '<b>Bước 2 — HOD:</b> xem KPI cấp dưới, chấm điểm quản lý, gửi lên GM.',
        '<b>Bước 3 — Giám đốc:</b> xem toàn bộ, <b>chốt điểm cuối cùng</b> — quyết định phân loại hiệu suất.',
    ], st))
    story.extend(steps([
        ('Mở module KPI', 'Menu KPI.'),
        ('Xem bảng cá nhân / team', 'Nhân viên thấy bảng của mình; HOD/GM thấy thêm phần duyệt KPI nhân viên.'),
        ('Chấm / chốt điểm', 'Nhập điểm tại cột kỳ đang mở (ô trắng = mở, ô xám = khóa). Bấm Lưu/Nộp.'),
        ('Quản lý kỳ (Admin)', 'Superuser/HR mở hoặc đóng từng kỳ Q1–Q4; import Excel khi giao KPI hàng loạt.'),
    ], st))
    story.extend(img('09-kpi.png', 'Trang KPI — ma trận chấm điểm theo quý (có thể kéo ngang trên mobile).', st))

    # === 6. DAO TAO ===
    story.append(PageBreak())
    story.append(P('6. Đào tạo E-Learning', 'h1', st))
    story.extend(steps([
        ('Nhân viên vào Học', 'Menu Đào tạo hoặc thẻ Học tập trên trang chủ / bottom nav.'),
        ('Chọn khóa', 'Lọc: Tất cả · Đang học · Chưa bắt đầu · Đã hoàn thành.'),
        ('Học bài', 'Mở khóa → chương → bài (video, PDF, bài đọc). Đánh dấu hoàn thành từng bài.'),
        ('Thi cuối khóa', 'Một số khóa gắn bài kiểm tra — phải đạt mới hoàn thành.'),
    ], st))
    story.extend(img('07-dao-tao.png', 'Không gian học tập — danh sách khóa và tiến độ %.', st))
    story.append(P('HR quản lý khóa học tại Training → Admin: tạo khóa, thêm chương/bài, gán học viên theo chức danh.', 'body', st))
    story.extend(img('14-khoa-hoc-admin.png', 'Quản lý khóa học (HR) — danh sách và cấu hình nội dung.', st))

    # === 7. KIEM TRA ===
    story.append(P('7. Kiểm tra năng lực', 'h1', st))
    story.extend(steps([
        ('Vào Kiểm tra', 'Menu hoặc thẻ Kiểm tra trên trang chủ.'),
        ('Làm bài', 'Chọn đề đang mở, làm trong khung thời gian quy định.'),
        ('Xem kết quả', 'Trắc nghiệm chấm ngay; tự luận chờ HR chấm.'),
    ], st))
    story.extend(img('08-kiem-tra.png', 'Danh sách bài thi / đánh giá năng lực.', st))

    # === 8. QUAN TRI ===
    story.append(PageBreak())
    story.append(P('8. Quản trị hệ thống (HR / Ban quản lý)', 'h1', st))
    story.append(P(
        'Tài khoản có quyền <b>quản trị portal (is_staff)</b> — thường là HR, IT — '
        'thấy thêm menu Tuyển dụng, Đào tạo, Kiểm tra, Nhân sự và Bảng điều khiển.',
        'body', st))
    story.append(P('8.1 Bảng điều khiển (Dashboard)', 'h2', st))
    story.append(P('Tổng quan số liệu KPI, đề thi, khóa học, tuyển dụng; chuyển tab nhanh giữa các module.', 'body', st))
    story.extend(img('10-dashboard.png', 'Dashboard quản trị — tab tổng quan.', st))
    story.append(P('8.2 Quản lý nhân sự', 'h2', st))
    story.extend(bullets([
        'Thêm/sửa/xóa tài khoản, phân vai trò EMPLOYEE / HOD / GM',
        'Gán danh sách cấp dưới cho tổ trưởng (HOD)',
        'Import/Export Excel hàng loạt, reset mật khẩu',
    ], st))
    story.extend(img('11-nhan-su.png', 'Danh sách nhân sự và thao tác quản lý.', st))
    story.append(P('8.3 Tuyển dụng', 'h2', st))
    story.extend(bullets([
        'Đăng tin tuyển dụng, quản lý vị trí và hạn nộp',
        'Kanban ứng viên: kéo thả Mới → Xem xét → Phỏng vấn → Trúng tuyển',
        'Lịch phỏng vấn, ghi chú HR, quản lý CCHN (ứng viên y tế)',
        'Ứng viên trúng tuyển → <b>Tạo User</b> tự động sinh tài khoản @justplay.vn',
    ], st))
    story.extend(img('13-vi-tri-tuyen-dung.png', 'Danh sách vị trí tuyển dụng đang mở.', st))
    story.extend(img('12-kanban.png', 'Bảng Kanban theo dõi ứng viên theo giai đoạn.', st))

    # === 9. PHAN QUYEN ===
    story.append(PageBreak())
    story.append(P('9. Phân quyền trong tổ chức', 'h1', st))
    t2 = Table([
        ['Vai trò', 'Báo cáo', 'KPI', 'Quản trị'],
        ['Nhân viên', 'Nộp BC cá nhân', 'Tự chấm KPI', 'Không'],
        ['HOD', 'Xem team', 'Chấm KPI cấp dưới', 'Không'],
        ['GM', 'Xem toàn công ty', 'Chốt KPI', 'Có (staff)'],
        ['HR/IT', 'Xem toàn công ty', 'Import, mở kỳ', 'Đầy đủ'],
    ], colWidths=[2.5 * cm, 4 * cm, 4 * cm, 4 * cm])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD), ('FONTNAME', (0, 1), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 8))
    story.append(P(
        'GM khi được gán vai trò Giám đốc trong hệ thống sẽ tự có quyền quản trị cao (staff/superuser) '
        'để xem toàn bộ dữ liệu và chốt KPI.',
        'tip', st))

    # === 10. HUONG DAN ===
    story.append(P('10. Hướng dẫn sử dụng trên portal', 'h1', st))
    story.append(P(
        'Trên menu có mục <b>Hướng dẫn</b> — tài liệu chi tiết cho nhân viên xưởng, tổ trưởng và HR. '
        'HOD/GM/HR có thể chỉnh sửa nội dung hướng dẫn trực tiếp trên portal (CKEditor).',
        'body', st))
    story.extend(img('15-huong-dan.png', 'Trang hướng dẫn sử dụng — mục lục và nội dung từng bước.', st))

    # === 11. HA TANG ===
    story.append(PageBreak())
    story.append(P('11. Hạ tầng và bảo mật', 'h1', st))
    story.extend(bullets([
        'Triển khai: Docker trên VPS — PostgreSQL, Gunicorn, Nginx',
        'Domain: portal.justplay.vn — hỗ trợ HTTPS (Let\'s Encrypt)',
        'Khóa tài khoản sau nhiều lần đăng nhập sai',
        'Bắt buộc đổi mật khẩu lần đầu',
        'Deploy: script deploy.sh — pull code, migrate, collectstatic',
        'Hỗ trợ kỹ thuật: support@justplay.vn',
    ], st))

    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(P(
        f'© JustPlay.vn · Tài liệu nội bộ · portal.justplay.vn · {date.today().strftime("%d/%m/%Y")}',
        'footer', st))

    doc.build(story)
    print(f'Created: {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    build()
