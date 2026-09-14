#!/usr/bin/env python3
"""Xuất PDF: đánh giá thay Tailscale bằng FortiClient VPN (FortiGate 60F).

Chạy: python scripts/generate_tailscale_vs_forticlient_pdf.py
"""

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
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs' / 'Tailscale_vs_FortiClient_FortiGate60F.pdf'

FONT_REG = 'JPBody'
FONT_BOLD = 'JPBodyBold'
FONT_MONO = 'Courier'

RED = colors.HexColor('#dc2626')
SLATE = colors.HexColor('#1e293b')
BODY = colors.HexColor('#334155')
MUTED = colors.HexColor('#64748b')
LINE = colors.HexColor('#e2e8f0')


def _register_fonts() -> None:
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


def _styles() -> dict:
    getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'Title', fontName=FONT_BOLD, fontSize=19, leading=24,
            textColor=RED, alignment=TA_CENTER, spaceAfter=4,
        ),
        'subtitle': ParagraphStyle(
            'Subtitle', fontName=FONT_REG, fontSize=10.5, leading=14,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=14,
        ),
        'h1': ParagraphStyle(
            'H1', fontName=FONT_BOLD, fontSize=13.5, leading=17,
            textColor=RED, spaceBefore=14, spaceAfter=7,
        ),
        'h2': ParagraphStyle(
            'H2', fontName=FONT_BOLD, fontSize=11, leading=14,
            textColor=SLATE, spaceBefore=9, spaceAfter=5,
        ),
        'body': ParagraphStyle(
            'Body', fontName=FONT_REG, fontSize=9.5, leading=13.5,
            textColor=BODY, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        'bullet': ParagraphStyle(
            'Bullet', fontName=FONT_REG, fontSize=9.5, leading=13.5,
            textColor=BODY, spaceAfter=3,
        ),
        'callout': ParagraphStyle(
            'Callout', fontName=FONT_REG, fontSize=9.5, leading=13.5,
            textColor=SLATE, leftIndent=10, rightIndent=10,
            backColor=colors.HexColor('#fef2f2'), borderPadding=9,
            borderColor=RED, borderWidth=0, spaceBefore=4, spaceAfter=9,
        ),
        'note': ParagraphStyle(
            'Note', fontName=FONT_REG, fontSize=8.5, leading=12,
            textColor=MUTED, spaceBefore=2, spaceAfter=8,
        ),
        'code': ParagraphStyle(
            'Code', fontName=FONT_MONO, fontSize=8.5, leading=12,
            textColor=SLATE, backColor=colors.HexColor('#f8fafc'),
            borderPadding=7, leftIndent=4, spaceBefore=3, spaceAfter=8,
        ),
        'footer': ParagraphStyle(
            'Footer', fontName=FONT_REG, fontSize=7.5, textColor=colors.grey,
            alignment=TA_CENTER,
        ),
    }


def _table(data, col_widths=None, align_first_left=True):
    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    style = [
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REG),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('LEADING', (0, 0), (-1, -1), 11.5),
        ('BACKGROUND', (0, 0), (-1, 0), RED),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if align_first_left:
        style.append(('FONTNAME', (0, 1), (0, -1), FONT_BOLD))
    t.setStyle(TableStyle(style))
    return t


def _bullets(items, st):
    return ListFlowable(
        [ListItem(Paragraph(x, st['bullet']), leftIndent=12) for x in items],
        bulletType='bullet', bulletChar='•', bulletFontSize=8,
        leftIndent=12, spaceAfter=7,
    )


def _rule():
    return HRFlowable(width='100%', thickness=0.6, color=LINE,
                      spaceBefore=4, spaceAfter=8)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT_REG, 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(
        A4[0] / 2, 1.1 * cm,
        f'JustPlay Portal — Nội bộ · Trang {doc.page}',
    )
    canvas.restoreState()


def build_pdf() -> Path:
    _register_fonts()
    st = _styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        leftMargin=1.9 * cm, rightMargin=1.9 * cm,
        topMargin=1.7 * cm, bottomMargin=1.9 * cm,
        title='Thay Tailscale bằng FortiClient VPN — Đánh giá kỹ thuật',
        author='IT — JustPlay Portal',
    )

    s: list = []
    s.append(Paragraph('Thay Tailscale bằng FortiClient VPN?', st['title']))
    s.append(Paragraph(
        f'Đánh giá kỹ thuật cho hạ tầng JustPlay Portal · FortiGate 60F · '
        f'{date.today().strftime("%d/%m/%Y")}',
        st['subtitle'],
    ))
    s.append(_rule())

    # --- Kết luận ---
    s.append(Paragraph('1. Kết luận ngắn', st['h1']))
    s.append(Paragraph(
        'Thay được, nhưng <b>không nên thay bằng FortiClient</b>. Câu trả lời khác nhau '
        'cho hai nhóm luồng riêng biệt:',
        st['body'],
    ))
    s.append(_bullets([
        '<b>VPS ↔ NAS</b> (5/6 luồng, toàn bộ phần code phụ thuộc): FortiClient là sai '
        'công cụ. Nếu muốn gom về FortiGate thì phải dùng <b>IPsec site-to-site</b>.',
        '<b>Máy nhân viên ↔ NAS khi ở ngoài văn phòng</b> (1 luồng, không có code phụ '
        'thuộc): FortiClient <b>tốt hơn</b> Tailscale. Đây đúng là việc con 60F sinh ra để làm.',
    ], st))

    # --- Tailscale đang làm gì ---
    s.append(Paragraph('2. Tailscale hiện đang chở những luồng nào', st['h1']))
    s.append(_table([
        ['Giao thức', 'Hướng', 'Dùng cho', 'Chạy ở đâu'],
        ['SMB 445\n(rclone + mount)', 'VPS → NAS', 'Lưu trữ file toàn portal', 'Request + job nền'],
        ['HTTPS 5556\n(DSM Web API)', 'VPS → NAS', 'Giám sát NAS; fallback upload/download', 'Request web'],
        ['SSH (paramiko)', 'VPS → NAS', 'Áp quyền ACL, tạo user/group local', 'Request + job nền'],
        ['LDAP 636', 'VPS → NAS', 'Đồng bộ tài khoản Portal → Directory Server', 'Request web'],
        ['HTTP 39280', 'VPS → NAS', 'WoL relay — bật máy tính từ xa', 'Request web'],
        ['WebDAV 5678 /\nSMB 445', 'PC nhân viên\n→ NAS', 'Map ổ đĩa NAS trên máy nhân viên', 'Không qua VPS'],
    ], col_widths=[3.1 * cm, 2.5 * cm, 6.9 * cm, 4.6 * cm]))
    s.append(Paragraph(
        'Năm luồng đầu là server-to-server, cần kết nối luôn bật. Luồng cuối là client, '
        'không có dòng code nào phụ thuộc — portal chỉ phát script cài RaiDrive.',
        st['note'],
    ))

    # --- Vì sao không dùng FortiClient ---
    s.append(Paragraph('3. Vì sao FortiClient không dùng được cho VPS ↔ NAS', st['h1']))

    s.append(Paragraph('3.1. SSL-VPN tunnel mode trên 60F là đường cụt', st['h2']))
    s.append(Paragraph(
        'Đây là lý do quyết định. Từ FortiOS 7.6.3, Fortinet đã bỏ SSL-VPN tunnel mode '
        'trên mọi model; cấu hình cũ không được nâng cấp qua và không dựng lại được vì '
        'tính năng đã bị loại khỏi cả GUI lẫn CLI. Riêng với 60F còn nặng hơn: release '
        'notes 7.6.1 ghi SSL-VPN bị bỏ trên các model 2GB RAM cho <b>cả</b> tunnel và web '
        'mode, và bản 7.6.3 nêu rõ Agentless VPN (tên mới của SSL-VPN web mode) không hỗ '
        'trợ trên dòng 40F, 60F, 90G. FortiGate 60F đúng là máy 2GB RAM. Hướng dẫn chính '
        'thức của Fortinet là chuyển sang IPsec.',
        st['body'],
    ))
    s.append(Paragraph(
        '<b>Hệ quả:</b> nếu dựng hạ tầng quanh FortiClient SSL-VPN, lần nâng firmware tới '
        'là mất kết nối toàn bộ — không có đường lùi bằng cấu hình.',
        st['callout'],
    ))

    s.append(Paragraph('3.2. FortiClient là app phiên người dùng, không phải daemon máy chủ', st['h2']))
    s.append(Paragraph(
        'Trên VPS Ubuntu sẽ phải chạy openfortivpn hoặc FortiClient Linux dưới systemd và '
        'tự viết logic reconnect. Tunnel là PPP-over-TLS — thông lượng và độ ổn định kém '
        'hơn WireGuard/IPsec rõ rệt, trong khi tải chính ở đây là SMB (rclone mount + '
        'backup DB/source/media lúc 00:00). SMB rất nhạy với đứt quãng và MTU.',
        st['body'],
    ))

    s.append(Paragraph('3.3. Chiều kết nối và NAT', st['h2']))
    s.append(Paragraph(
        'Tailscale là peer-to-peer, tự xuyên NAT, không quan tâm IP động. Với FortiGate, '
        'VPS phải dial vào IP công cộng của 60F → cần IP tĩnh hoặc DDNS. Công ty có 4 '
        'đường của 4 nhà mạng khác nhau, cần chắc đường ở văn phòng chính có IP tĩnh.',
        st['body'],
    ))

    s.append(Paragraph('3.4. Tunnel kém ổn định làm tăng rủi ro treo worker', st['h2']))
    s.append(Paragraph(
        'Khi NAS mất kết nối, mọi I/O trên mount FUSE rơi vào trạng thái D '
        '(uninterruptible sleep) — không kill được kể cả bằng gunicorn --timeout. Portal '
        'đã được bổ sung lớp bảo vệ cho tình huống này, nhưng bảo vệ chỉ là suy giảm mềm. '
        'Đổi sang một tunnel kém ổn định hơn là tự tăng tần suất sự cố.',
        st['body'],
    ))

    s.append(Paragraph('3.5. Lịch sử bảo mật', st['h2']))
    s.append(Paragraph(
        'SSL-VPN của FortiGate là mục tiêu bị khai thác thường xuyên trong vài năm qua. '
        'Đây là thêm một lý do để chọn IPsec nếu đi đường FortiGate.',
        st['body'],
    ))

    # --- Phương án IPsec ---
    s.append(Paragraph('4. Nếu vẫn muốn gom hết về FortiGate: IPsec site-to-site', st['h1']))
    s.append(Paragraph(
        'Phương án đúng là VPS chạy strongSwan làm dial-up client tới 60F — không dùng '
        'FortiClient.',
        st['body'],
    ))
    s.append(_table([
        ['Tiêu chí', 'Tailscale (hiện tại)', 'IPsec site-to-site (60F)'],
        ['IP tĩnh ở văn phòng', 'Không cần', 'Cần (hoặc DDNS)'],
        ['Xuyên NAT / CGNAT', 'Tự động', 'Phải mở port trên WAN'],
        ['Cấu hình VPS', 'tailscale up', 'strongSwan + tuning MTU/MSS'],
        ['Tự kết nối lại', 'Tự động', 'Phụ thuộc DPD/keepalive'],
        ['Policy & log tập trung', 'Không', 'Có, trên FortiGate'],
        ['Phụ thuộc SaaS bên thứ ba', 'Có (control plane)', 'Không'],
        ['Crypto offload', 'Không', 'Có (60F có NP/CP)'],
        ['Fallback khi P2P thất bại', 'DERP relay', 'Không có'],
    ], col_widths=[5.2 * cm, 5.9 * cm, 6.0 * cm]))
    s.append(Paragraph(
        '<b>Được:</b> mọi thứ dưới quyền IT, log và policy tập trung, bỏ phụ thuộc dịch vụ '
        'ngoài. <b>Mất:</b> nhiều việc cấu hình hơn, phải tune MTU/MSS clamping cho SMB, '
        'không còn fallback relay.',
        st['body'],
    ))
    s.append(Paragraph(
        'Lưu ý dung lượng: 60F là máy entry-level và đang gánh UTM cho cả văn phòng. Job '
        'backup 00:00 đẩy DB + source + media qua tunnel sẽ đi xuyên nó — nên đo thử trước '
        'khi chốt. Nếu firmware đã có WireGuard interface thì đó là lựa chọn tốt hơn IPsec '
        'cho chặng này, nhưng cần kiểm tra trên máy thật xem 60F/firmware hiện tại có hỗ '
        'trợ không.',
        st['body'],
    ))

    # --- Chỗ FortiClient nên dùng ---
    s.append(Paragraph('5. Chỗ FortiClient thực sự nên dùng', st['h1']))
    s.append(Paragraph(
        'Chuyển <b>máy nhân viên</b> từ Tailscale sang FortiClient IPsec VPN. Ở đây '
        'FortiClient hơn Tailscale rõ ràng:',
        st['body'],
    ))
    s.append(_bullets([
        'Policy theo từng user, MFA bằng FortiToken.',
        'Xác thực nối vào Synology Directory Server đã có — cùng một account portal, đúng '
        'nhóm phòng ban, không phải cấp thêm tài khoản Tailscale cho từng người.',
        'IT thu hồi quyền tập trung khi nhân viên nghỉ, không phụ thuộc tài khoản cá nhân.',
        'Nhân viên chỉ cài một client thay vì hai.',
        'FortiClient VPN-only bản miễn phí có IPsec; không cần license nếu không dùng EMS.',
    ], st))
    s.append(Paragraph(
        'Luồng này không có code phụ thuộc. Chỉ cần đổi <font name="Courier">'
        'NAS_RDRIVE_FALLBACK_SERVER</font> và cập nhật phần hướng dẫn trong '
        '<font name="Courier">scripts/JustPlay-NAS-RaiDrive-Setup.ps1</font>.',
        st['body'],
    ))

    # --- Khối lượng công việc ---
    s.append(Paragraph('6. Khối lượng công việc phía code nếu đổi chặng VPS ↔ NAS', st['h1']))
    s.append(Paragraph(
        'Ít hơn dự kiến — <b>không phải sửa dòng Python nào</b>, nhờ phần refactor đã làm: '
        'host NAS giờ suy ra từ một chỗ duy nhất.',
        st['body'],
    ))
    s.append(_bullets([
        '<font name="Courier">.env</font>: đổi <font name="Courier">NAS_DSM_URL</font> sang '
        'IP LAN của NAS. <font name="Courier">NAS_SSH_HOST</font> và '
        '<font name="Courier">NAS_LDAP_HOST</font> tự suy ra từ đây nếu để trống.',
        '<font name="Courier">.env</font>: đổi '
        '<font name="Courier">RUSTDESK_WOL_RELAY_URL</font> sang IP mới.',
        'Chạy lại <font name="Courier">bash scripts/setup-rclone-nas.sh</font> — bản mới lấy '
        'host SMB từ <font name="Courier">NAS_DSM_URL</font>, không còn hardcode, và có '
        'precheck cổng 445 với timeout 10s nên sai IP là báo lỗi ngay thay vì treo.',
        'Thêm route trên VPS tới subnet LAN của NAS.',
    ], st))
    s.append(Paragraph(
        'Tức là một biến <font name="Courier">NAS_DSM_URL</font> quyết định cả 4 luồng '
        'DSM / SSH / LDAP / SMB. Trước đây rclone hardcode IP riêng — chính là nguyên nhân '
        'sự cố deploy bị treo.',
        st['body'],
    ))

    # --- Đề xuất ---
    s.append(Paragraph('7. Đề xuất lộ trình', st['h1']))
    s.append(Paragraph(
        'Làm ba giai đoạn, không đổi cùng lúc:',
        st['body'],
    ))
    s.append(_table([
        ['#', 'Việc', 'Lý do / rủi ro'],
        ['1', 'Xử lý sự cố NAS đang có trước',
         'rclone hiện không tới được NAS; nghi do IP Tailscale lệch (100.93.5.42 trong '
         'script cũ vs 100.90.91.74 trong .env). Không đổi hạ tầng khi đang có sự cố.'],
        ['2', 'Chuyển nhân viên sang FortiClient IPsec',
         'Giá trị cao, rủi ro thấp, không đụng code.'],
        ['3', 'Chặng VPS ↔ NAS: giữ Tailscale',
         'Đây là chỗ Tailscale làm tốt nhất. Chỉ chuyển sang IPsec site-to-site nếu có yêu '
         'cầu bắt buộc không dùng dịch vụ bên thứ ba, hoặc cần log/policy tập trung. '
         'Dứt khoát không dùng FortiClient cho chặng này.'],
    ], col_widths=[1.0 * cm, 5.3 * cm, 10.8 * cm], align_first_left=False))

    s.append(_rule())
    s.append(Paragraph(
        'Nguồn tham khảo về việc Fortinet bỏ SSL-VPN: Fortinet Community — '
        '“Changes on SSL VPN modes starting from v7.6.3” và “SSL VPN does not connect when '
        'the FortiGate is on v7.6.3”; FortiOS 7.6.1 / 7.6.3 Release Notes. '
        'Nội dung từ các nguồn này đã được diễn giải lại để tuân thủ điều kiện bản quyền.',
        st['note'],
    ))
    s.append(Paragraph(
        'Thông tin về hỗ trợ WireGuard trên 60F chưa được xác minh trên thiết bị thật — '
        'cần kiểm tra firmware hiện hành trước khi đưa vào phương án.',
        st['note'],
    ))

    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return OUTPUT


if __name__ == '__main__':
    path = build_pdf()
    print(f'Đã tạo: {path}')
