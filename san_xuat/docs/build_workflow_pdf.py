"""Generate detailed PDF: Quy trình sản xuất Portal JustPlay (ít viết tắt, thao tác từng màn)."""
from __future__ import annotations

from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

pdfmetrics.registerFont(TTFont("VN", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("VN-B", r"C:\Windows\Fonts\arialbd.ttf"))

OUT = Path(__file__).resolve().parent / "Quy_trinh_san_xuat_PortalJustPlay.pdf"

# Brand JustPlay — đỏ chủ đạo (không dùng xanh teal)
PRIMARY = HexColor("#dc2626")
ACCENT = HexColor("#b91c1c")
LIGHT = HexColor("#fef2f2")
BORDER = HexColor("#fecaca")
MUTED = HexColor("#64748b")
DARK = HexColor("#0f172a")
WARN = HexColor("#b45309")
BOX_BG = HexColor("#fff1f2")
BLUE = HexColor("#0284c7")
AMBER = HexColor("#d97706")
PINK = HexColor("#db2777")
PURPLE = HexColor("#7c3aed")
H2_COLOR = HexColor("#991b1b")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            fontName="VN-B",
            fontSize=20,
            leading=26,
            textColor=PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            fontName="VN",
            fontSize=11,
            leading=15,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1VN",
            fontName="VN-B",
            fontSize=13,
            leading=17,
            textColor=PRIMARY,
            spaceBefore=14,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2VN",
            fontName="VN-B",
            fontSize=11,
            leading=14,
            textColor=H2_COLOR,
            spaceBefore=10,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H3VN",
            fontName="VN-B",
            fontSize=10,
            leading=13,
            textColor=DARK,
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyVN",
            fontName="VN",
            fontSize=9.5,
            leading=13,
            textColor=DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BulletVN",
            fontName="VN",
            fontSize=9,
            leading=12.5,
            textColor=DARK,
            leftIndent=10,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallVN",
            fontName="VN",
            fontSize=8,
            leading=10.5,
            textColor=MUTED,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(name="CellVN", fontName="VN", fontSize=8, leading=10.5, textColor=DARK)
    )
    styles.add(
        ParagraphStyle(name="CellHead", fontName="VN-B", fontSize=8, leading=10.5, textColor=white)
    )
    styles.add(
        ParagraphStyle(
            name="NoteVN",
            fontName="VN",
            fontSize=8.5,
            leading=11.5,
            textColor=HexColor("#334155"),
            leftIndent=6,
            spaceAfter=4,
            backColor=LIGHT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TOC",
            fontName="VN",
            fontSize=10,
            leading=16,
            textColor=DARK,
            leftIndent=8,
        )
    )
    return styles


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1.2)
    canvas.line(1.6 * cm, A4[1] - 1.15 * cm, A4[0] - 1.6 * cm, A4[1] - 1.15 * cm)
    canvas.setFont("VN", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.6 * cm, A4[1] - 0.95 * cm, "Portal JustPlay — Module Sản xuất")
    canvas.drawRightString(A4[0] - 1.6 * cm, A4[1] - 0.95 * cm, "Hướng dẫn quy trình & thao tác màn hình")
    canvas.line(1.6 * cm, 1.2 * cm, A4[0] - 1.6 * cm, 1.2 * cm)
    canvas.drawCentredString(A4[0] / 2, 0.7 * cm, f"Trang {doc.page}")
    canvas.restoreState()


def make_flow_box(d, x, y, w, h, text, fill=BOX_BG, stroke=ACCENT):
    d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=stroke, strokeWidth=1, rx=3, ry=3))
    lines = text.split("\n")
    total_h = len(lines) * 8.5
    start_y = y + h / 2 + total_h / 2 - 6.5
    for i, line in enumerate(lines):
        d.add(
            String(
                x + w / 2,
                start_y - i * 8.5,
                line,
                fontName="VN",
                fontSize=6.5,
                fillColor=DARK,
                textAnchor="middle",
            )
        )


def arrow_down(d, x, y):
    d.add(Line(x, y + 9, x, y + 2, strokeColor=PRIMARY, strokeWidth=1.1))
    d.add(Polygon([x - 2.5, y + 3.5, x + 2.5, y + 3.5, x, y], fillColor=PRIMARY, strokeColor=PRIMARY))


def build_workflow_drawing():
    w, h = 500, 500
    d = Drawing(w, h)
    d.add(
        String(
            w / 2,
            h - 12,
            "LUỒNG NGHIỆP VỤ CHÍNH",
            fontName="VN-B",
            fontSize=8.5,
            fillColor=PRIMARY,
            textAnchor="middle",
        )
    )
    bw, bh = 155, 34
    cx = w / 2 - bw / 2
    steps = [
        (h - 52, "0. Dữ liệu gốc\nĐịnh mức BOM · Kho NPL · KiotViet · Tổ/chuyền", HexColor("#e0f2fe"), BLUE),
        (h - 102, "1. Kế hoạch tổng thể\nThêm sản phẩm → Xác nhận", BOX_BG, ACCENT),
        (h - 152, "2. Kế hoạch nguyên phụ liệu\nTách định mức → Xác nhận / Mua hàng", BOX_BG, ACCENT),
        (h - 202, "3. Kế hoạch chi tiết\nPhân bổ ngày/chuyền → Sinh lệnh", BOX_BG, ACCENT),
        (h - 252, "4. Lệnh sản xuất\nLưu nháp → Phát hành", HexColor("#fef3c7"), AMBER),
        (h - 302, "5. Xuất vật tư\nTạo yêu cầu → Duyệt → Phiếu xuất kho", HexColor("#fef3c7"), AMBER),
        (h - 352, "6. Thống kê sản xuất\nGhi sản lượng công đoạn → Xác nhận", HexColor("#fef3c7"), AMBER),
        (h - 402, "7. Kiểm tra chất lượng → Nhập thành phẩm → Đóng gói", HexColor("#fce7f3"), PINK),
        (h - 452, "8. Truy xuất nguồn gốc\nTheo lệnh sản xuất hoặc mã lô", HexColor("#f3e8ff"), PURPLE),
    ]
    for i, (y, text, fill, stroke) in enumerate(steps):
        make_flow_box(d, cx, y, bw, bh, text, fill, stroke)
        if i < len(steps) - 1:
            arrow_down(d, w / 2, steps[i + 1][0] + bh)
    return d


def _table(rows, col_widths, header=True):
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style_cmds = [
        ("BOX", (0, 0), (-1, -1), 0.7, PRIMARY),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    if header:
        style_cmds.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT]),
            ]
        )
    else:
        style_cmds.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, LIGHT]))
    t.setStyle(TableStyle(style_cmds))
    return t


def P(text, style):
    return Paragraph(text, style)


def screen_block(story, styles, title, url, lifecycle, actions, notes=None):
    """One screen section."""
    parts = []
    parts.append(P(title, styles["H3VN"]))
    parts.append(P(f"<b>Đường dẫn:</b> {url}", styles["BulletVN"]))
    if lifecycle:
        parts.append(P(f"<b>Trạng thái:</b> {lifecycle}", styles["BulletVN"]))
    parts.append(P("<b>Thao tác được phép:</b>", styles["BulletVN"]))
    for a in actions:
        parts.append(P(f"• {a}", styles["BulletVN"]))
    if notes:
        parts.append(P(f"<i>Ghi chú:</i> {notes}", styles["BulletVN"]))
    parts.append(Spacer(1, 0.15 * cm))
    story.append(KeepTogether(parts))


def build():
    styles = _styles()
    story = []
    c = styles["CellVN"]
    h = styles["CellHead"]

    # ========== COVER ==========
    story.append(Spacer(1, 1.8 * cm))
    story.append(P("PORTAL JUSTPLAY", styles["CoverSub"]))
    story.append(P("Quy trình sản xuất", styles["CoverTitle"]))
    story.append(
        P(
            "Hướng dẫn nghiệp vụ chi tiết — thao tác từng màn hình",
            styles["CoverSub"],
        )
    )
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        HRFlowable(width="80%", thickness=2, color=ACCENT, spaceBefore=4, spaceAfter=4, hAlign="CENTER")
    )
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        P(
            "Tài liệu mô tả luồng từ kế hoạch đến truy xuất nguồn gốc, "
            "thao tác từng màn hình, và cách cấu hình <b>Thiết lập chung</b> module Sản xuất.",
            styles["SmallVN"],
        )
    )
    story.append(P("Ngày cập nhật: 21/07/2026 · Phiên bản chi tiết (+ thiết lập chung)", styles["SmallVN"]))
    story.append(Spacer(1, 0.9 * cm))

    cover_info = [
        [
            P("<b>Phạm vi</b>", c),
            P(
                "Kế hoạch → Điều phối → Chất lượng → Nhập thành phẩm → Đóng gói → Truy xuất · Thiết lập chung",
                c,
            ),
        ],
        [
            P("<b>Đối tượng đọc</b>", c),
            P("Điều phối sản xuất, kho nguyên phụ liệu, kiểm tra chất lượng, quản lý xưởng, admin cấu hình", c),
        ],
        [
            P("<b>Hệ thống liên quan</b>", c),
            P("Kho nguyên phụ liệu · KiotViet (thành phẩm) · Hồ sơ định mức BOM", c),
        ],
        [
            P("<b>Quyền module</b>", c),
            P(
                "<b>Xem</b> — vào màn hình · <b>Tạo</b> — nút Thêm/Tạo · "
                "<b>Sửa</b> — xác nhận, duyệt, phát hành, chốt, <b>lưu thiết lập chung</b>",
                c,
            ),
        ],
    ]
    t = Table(cover_info, colWidths=[3.8 * cm, 12.2 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 1, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t)

    story.append(Spacer(1, 0.7 * cm))
    story.append(P("Mục lục", styles["H2VN"]))
    toc_items = [
        "1. Quy ước thuật ngữ & quyền thao tác",
        "2. Tổng quan luồng nghiệp vụ",
        "3. Chuẩn bị dữ liệu gốc",
        "4. Kế hoạch (tổng thể, nguyên phụ liệu, chi tiết, mua hàng)",
        "5. Điều phối sản xuất (lệnh, xuất vật tư, thống kê, nhập thành phẩm…)",
        "6. Chất lượng",
        "7. Đóng gói, truy xuất, giao việc, năng lực, xưởng, gia công",
        "8. Giá thành (tóm tắt)",
        "9. Thiết lập chung — hướng dẫn cấu hình",
        "10. Checklist thao tác theo thứ tự",
        "11. Ghi chú kỹ thuật",
    ]
    for item in toc_items:
        story.append(P(item, styles["TOC"]))

    story.append(PageBreak())

    # ========== 1. THUẬT NGỮ ==========
    story.append(P("1. Quy ước thuật ngữ & quyền thao tác", styles["H1VN"]))
    story.append(
        P(
            "Tài liệu ưu tiên dùng tên đầy đủ. Bảng dưới chỉ để đối chiếu khi gặp mã ngắn trên giao diện cũ.",
            styles["BodyVN"],
        )
    )
    term_rows = [
        [P("<b>Tên đầy đủ</b>", h), P("<b>Mã ngắn (nếu có)</b>", h), P("<b>Ý nghĩa</b>", h)],
        [P("Kế hoạch tổng thể", c), P("KHTT", c), P("Kế hoạch sản xuất theo kỳ / sản phẩm", c)],
        [P("Kế hoạch nguyên phụ liệu", c), P("KHNVL", c), P("Nhu cầu NPL tách từ định mức BOM", c)],
        [P("Kế hoạch chi tiết", c), P("KHCT", c), P("Phân bổ theo ngày / tổ chuyền", c)],
        [P("Lệnh sản xuất", c), P("LSX", c), P("Lệnh thực thi sản xuất một sản phẩm", c)],
        [P("Yêu cầu xuất vật tư", c), P("YCX", c), P("Yêu cầu lấy nguyên phụ liệu từ kho", c)],
        [P("Thống kê sản xuất", c), P("TKSX", c), P("Ghi nhận sản lượng theo công đoạn", c)],
        [P("Yêu cầu nhập thành phẩm", c), P("YCNTP", c), P("Yêu cầu nhập hàng thành phẩm", c)],
        [P("Bán thành phẩm", c), P("BTP", c), P("Bán thành phẩm giữa các công đoạn", c)],
        [P("Yêu cầu kiểm tra chất lượng", c), P("YCKT / QC", c), P("Yêu cầu kiểm hàng", c)],
        [P("Phiếu kiểm tra", c), P("PKT", c), P("Phiếu ghi kết quả kiểm tra", c)],
        [P("Định mức nguyên liệu", c), P("BOM", c), P("Bill of Materials — cấu trúc nguyên liệu", c)],
        [P("Nguyên phụ liệu", c), P("NPL", c), P("Nguyên liệu / phụ liệu sản xuất", c)],
    ]
    story.append(_table(term_rows, [4.5 * cm, 3.2 * cm, 8.3 * cm]))

    story.append(P("1.1. Ba mức quyền trên module Sản xuất", styles["H2VN"]))
    story.append(
        P(
            "• <b>Xem:</b> vào danh sách / chi tiết, lọc, tra cứu — không đổi trạng thái chứng từ.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• <b>Tạo:</b> hiện nút “Thêm / Tạo …”, mở form tạo chứng từ mới.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• <b>Sửa (cập nhật):</b> xác nhận, phát hành, duyệt, gửi, chốt, hoàn thành, từ chối… "
            "trên màn chi tiết hoặc form thao tác.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "Hầu hết màn quy trình chính <b>không có nút Xóa hàng loạt</b>. "
            "Một số chứng từ hỗ trợ Hủy / Từ chối theo trạng thái.",
            styles["BodyVN"],
        )
    )

    # ========== 2. TỔNG QUAN ==========
    story.append(P("2. Tổng quan luồng nghiệp vụ", styles["H1VN"]))
    story.append(
        P(
            "Module Sản xuất quản lý vòng đời từ lập kế hoạch đến thành phẩm nhập kho và truy xuất. "
            "Luồng dưới đây là trình tự khuyến nghị khi vận hành thực tế.",
            styles["BodyVN"],
        )
    )
    story.append(build_workflow_drawing())
    story.append(Spacer(1, 0.2 * cm))

    story.append(P("2.1. Màn Tổng quan (dashboard)", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Tổng quan sản xuất",
        "/san-xuat/tong-quan/",
        "Không có vòng đời chứng từ (chỉ xem)",
        [
            "Lọc theo tháng hoặc khoảng ngày, mã sản phẩm, tổ/chuyền",
            "Xem tab: Tổng hợp · Lệnh sản xuất · Sản lượng · Chất lượng · Dừng chuyền",
            "Bấm liên kết sang báo cáo vận hành, lệnh sản xuất, cảnh báo, kế hoạch…",
            "<b>Không</b> có thao tác gửi form thay đổi dữ liệu",
        ],
        "Hub gốc /san-xuat/ tự chuyển về trang tổng quan.",
    )

    story.append(PageBreak())

    # ========== 3. MASTER DATA ==========
    story.append(P("3. Chuẩn bị dữ liệu gốc", styles["H1VN"]))
    story.append(
        P(
            "Trước khi mở lệnh sản xuất, cần đủ dữ liệu gốc. Thiếu định mức BOM đang kích hoạt "
            "hoặc thiếu tồn nguyên phụ liệu sẽ làm kẹt bước xuất vật tư.",
            styles["BodyVN"],
        )
    )
    master_rows = [
        [P("<b>Hạng mục</b>", h), P("<b>Đường dẫn</b>", h), P("<b>Được phép làm gì</b>", h)],
        [
            P("Hồ sơ sản xuất / Định mức BOM", c),
            P("/san-xuat/ho-so/ · /san-xuat/bom/", c),
            P("Xem danh sách; tạo hồ sơ (quyền Tạo); kích hoạt phiên bản BOM trong chi tiết hồ sơ", c),
        ],
        [
            P("Thành phẩm (KiotViet)", c),
            P("/san-xuat/kho-san-pham/hang-hoa/", c),
            P("Tra cứu hàng hóa, tồn, phiếu nhập — chủ yếu xem", c),
        ],
        [
            P("Kho nguyên phụ liệu", c),
            P("Module Kho NPL (liên kết từ hub Sản phẩm–NVL)", c),
            P("Nhập / xuất / xem tồn nguyên phụ liệu ngoài module Sản xuất", c),
        ],
        [
            P("Sản phẩm – nguyên phụ liệu (hub)", c),
            P("/san-xuat/san-pham-nvl/", c),
            P("Điều hướng sang hồ sơ, kho NPL, KiotViet, giá thành — không POST", c),
        ],
        [
            P("Tổ / chuyền (năng lực)", c),
            P("/san-xuat/nang-luc/", c),
            P("Xem tải năng lực theo kỳ; Thêm tổ/chuyền nếu có quyền Tạo", c),
        ],
    ]
    story.append(_table(master_rows, [4.2 * cm, 5.2 * cm, 6.6 * cm]))

    # ========== 4. KẾ HOẠCH ==========
    story.append(P("4. Kế hoạch", styles["H1VN"]))
    story.append(
        P(
            "Hub điều hướng: <b>/san-xuat/ke-hoach/</b> (chỉ liên kết danh mục, không gửi dữ liệu).",
            styles["BodyVN"],
        )
    )

    story.append(P("4.1. Kế hoạch tổng thể", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Danh sách kế hoạch tổng thể",
        "/san-xuat/ke-hoach/tong-the/",
        None,
        [
            "Xem / lọc danh sách (quyền Xem)",
            "Nút <b>Tạo</b> kế hoạch mới (quyền Tạo) → /ke-hoach/tong-the/them/",
        ],
    )
    screen_block(
        story,
        styles,
        "Chi tiết kế hoạch tổng thể",
        "/san-xuat/ke-hoach/tong-the/<mã>/",
        "Nháp → Đã xác nhận → (Hoàn thành / Hủy)",
        [
            "Khi <b>Nháp</b> + quyền Sửa: <b>Thêm dòng sản phẩm</b>",
            "Khi Nháp + quyền Sửa: <b>Import dòng từ đơn KiotViet</b>",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> kế hoạch tổng thể",
            "Khi đã xác nhận: liên kết <b>Lập kế hoạch chi tiết</b>",
            "Sau khi xác nhận: không còn thêm/sửa dòng như lúc nháp",
        ],
    )

    story.append(P("4.2. Kế hoạch nguyên phụ liệu", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Tạo kế hoạch nguyên phụ liệu (tách định mức)",
        "/san-xuat/ke-hoach/npl/them/",
        None,
        [
            "Chọn kế hoạch tổng thể đã có → nút <b>Explode → kế hoạch nguyên phụ liệu</b> (quyền Tạo)",
            "Hệ thống tính nhu cầu nguyên phụ liệu theo định mức BOM",
        ],
    )
    screen_block(
        story,
        styles,
        "Chi tiết kế hoạch nguyên phụ liệu",
        "/san-xuat/ke-hoach/npl/<mã>/",
        "Nháp → Đã xác nhận",
        [
            "Khi Nháp + quyền Sửa: <b>Cập nhật tồn / số lượng thiếu</b> (refresh)",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> kế hoạch nguyên phụ liệu",
            "Liên kết: <b>Tạo yêu cầu mua nguyên phụ liệu từ số lượng thiếu</b>",
        ],
        "Danh sách: /san-xuat/ke-hoach/npl/",
    )

    story.append(P("4.3. Kế hoạch chi tiết", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết kế hoạch chi tiết",
        "/san-xuat/ke-hoach/chi-tiet/<mã>/",
        "Nháp → Đã xác nhận",
        [
            "Tạo bằng explode từ kế hoạch tổng thể (quyền Tạo) tại /ke-hoach/chi-tiet/them/",
            "Khi Nháp + quyền Sửa: <b>Cập nhật phân bổ ngày</b>",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> kế hoạch chi tiết",
            "Khi <b>Đã xác nhận</b> + quyền Sửa: <b>Sinh lệnh sản xuất</b> từ kế hoạch chi tiết",
        ],
    )

    story.append(P("4.4. Yêu cầu mua nguyên phụ liệu", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết yêu cầu mua nguyên phụ liệu",
        "/san-xuat/ke-hoach/yeu-cau-mua-npl/<mã>/",
        "Nháp → Đã gửi → Đã duyệt | Từ chối",
        [
            "Tạo mới (quyền Tạo) tại /yeu-cau-mua-npl/them/",
            "Khi Nháp + quyền Sửa: <b>Gửi duyệt</b>",
            "Khi Đã gửi + quyền Sửa: <b>Duyệt</b> hoặc <b>Từ chối</b>",
            "Khi Đã duyệt: liên kết <b>Tạo đơn mua hàng</b>",
        ],
    )

    story.append(P("4.5. Đơn mua hàng", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết đơn mua hàng",
        "/san-xuat/ke-hoach/don-mua-hang/<mã>/",
        "Nháp → Đã xác nhận → Đã nhập",
        [
            "Tạo mới (quyền Tạo)",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> đơn mua hàng",
            "Quyền Sửa: <b>Liên kết phiếu nhập KiotViet</b>",
        ],
    )

    story.append(PageBreak())

    # ========== 5. ĐIỀU PHỐI ==========
    story.append(P("5. Điều phối sản xuất", styles["H1VN"]))
    story.append(
        P(
            "Hub điều hướng: <b>/san-xuat/dieu-phoi/</b>. Đây là phần vận hành chính của nhà máy.",
            styles["BodyVN"],
        )
    )

    story.append(P("5.1. Lệnh sản xuất", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Danh sách lệnh sản xuất",
        "/san-xuat/dieu-phoi/lenh-sx/",
        None,
        [
            "Xem / lọc danh sách lệnh",
            "Nút <b>Tạo lệnh</b> (quyền Tạo) — thường tạo từ định mức BOM (mã sản phẩm, số lượng, tổ)",
        ],
    )
    screen_block(
        story,
        styles,
        "Chi tiết lệnh sản xuất",
        "/san-xuat/dieu-phoi/lenh-sx/<mã>/",
        "Nháp → Đã phát hành → Đang sản xuất → Hoàn thành | Hủy",
        [
            "Khi <b>Nháp</b> + quyền Sửa: <b>Lưu</b> lệnh · <b>Phát hành</b> lệnh",
            "Khi Đã phát hành / Đang sản xuất / Hoàn thành + quyền Sửa: "
            "<b>Tạo yêu cầu xuất vật tư từ định mức BOM</b>",
            "Khi Đang sản xuất / Hoàn thành + quyền Sửa: <b>Tạo yêu cầu nhập thành phẩm</b>",
            "Liên kết: tạo thống kê sản xuất, bàn giao bán thành phẩm, xem cảnh báo chất lượng",
            "Xem tiến độ sản lượng, danh sách thống kê / xuất / nhập liên quan trên cùng màn",
        ],
        "Không phát hành thì không nên xuất vật tư / ghi sản lượng chính thức.",
    )

    story.append(P("5.2. Yêu cầu xuất vật tư", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết yêu cầu xuất vật tư",
        "/san-xuat/dieu-phoi/yeu-cau-xuat-vt/<mã>/",
        "Nháp / Đã gửi → Đã duyệt (kèm phiếu xuất kho nguyên phụ liệu)",
        [
            "Danh sách chỉ xem — <b>không có nút tạo độc lập</b>; tạo từ chi tiết lệnh sản xuất",
            "Khi chưa duyệt + quyền Sửa: <b>Duyệt</b> → sinh / post phiếu xuất kho nguyên phụ liệu "
            "(có thể kèm file đính kèm)",
            "Sau khi duyệt thành công: trạng thái yêu cầu hoàn tất, phiếu xuất đã ghi sổ",
        ],
    )

    story.append(P("5.3. Thống kê sản xuất", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết thống kê sản xuất",
        "/san-xuat/dieu-phoi/thong-ke-sx/<mã>/",
        "Nháp → Đã xác nhận",
        [
            "Tạo mới (quyền Tạo): chọn lệnh, ngày, công đoạn, số lượng đạt / lỗi, tổ",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> thống kê (cập nhật sản lượng trên lệnh; "
            "có thể sinh cảnh báo tỷ lệ lỗi)",
            "Sau xác nhận + quyền Sửa: <b>Tạo yêu cầu kiểm tra chất lượng</b> từ thống kê",
        ],
        "Có thể ghi nhận nhanh tại màn Xưởng (/san-xuat/shop-floor/) nếu có quyền Sửa.",
    )

    story.append(P("5.4. Yêu cầu nhập thành phẩm", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Chi tiết yêu cầu nhập thành phẩm",
        "/san-xuat/dieu-phoi/yeu-cau-nhap-tp/<mã>/",
        "Nháp → Đã gửi → Hoàn thành | Hủy",
        [
            "Tạo từ lệnh sản xuất hoặc form tạo riêng (quyền Tạo)",
            "Khi Nháp + quyền Sửa: <b>Gửi</b> yêu cầu",
            "Quyền Sửa: <b>Liên kết phiếu nhập KiotViet</b>",
        ],
    )

    story.append(P("5.5. Bàn giao & trả lại bán thành phẩm", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Bàn giao bán thành phẩm",
        "/san-xuat/dieu-phoi/ban-giao-btp/<mã>/",
        "Chờ bàn giao → Đã bàn giao | Từ chối",
        [
            "Tạo phiếu bàn giao (quyền Tạo): lệnh, công đoạn nguồn → đích, số lượng",
            "Khi Chờ bàn giao + quyền Sửa: <b>Xác nhận bàn giao</b> hoặc <b>Từ chối</b>",
        ],
    )
    screen_block(
        story,
        styles,
        "Trả lại bán thành phẩm",
        "/san-xuat/dieu-phoi/tra-lai-btp/<mã>/",
        "Nháp → Đã xác nhận | Hủy",
        [
            "Tạo phiếu trả (quyền Tạo), thường gắn bàn giao gốc + lý do",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> hoặc <b>Hủy</b>",
        ],
    )
    screen_block(
        story,
        styles,
        "Tình hình bàn giao sản xuất",
        "/san-xuat/dieu-phoi/tinh-hinh-ban-giao/",
        "Không (báo cáo / sổ tồn)",
        [
            "Xem tồn / thống kê bàn giao (chờ xử lý, đã xong, từ chối)",
            "<b>Không</b> có thao tác đổi trạng thái trên màn này",
        ],
    )

    story.append(P("5.6. Lịch sản xuất, nguyên phụ liệu thừa, lệnh tháo dỡ", styles["H2VN"]))
    screen_block(
        story,
        styles,
        "Lịch sản xuất",
        "/san-xuat/dieu-phoi/lich-sx/",
        None,
        [
            "Xem lịch theo tuần (tuần trước / tuần sau)",
            "Quyền Sửa: <b>Cập nhật lịch lệnh</b> (ngày bắt đầu / kết thúc dự kiến, tổ)",
        ],
    )
    screen_block(
        story,
        styles,
        "Nguyên phụ liệu thừa",
        "/san-xuat/dieu-phoi/npl-thua/<mã>/",
        "Nháp → Đã nhập kho | Hủy",
        [
            "Tạo phiếu (quyền Tạo)",
            "Khi Nháp + quyền Sửa: <b>Xác nhận nhập kho</b>",
        ],
    )
    screen_block(
        story,
        styles,
        "Lệnh tháo dỡ",
        "/san-xuat/dieu-phoi/lenh-thao-do/<mã>/",
        "Nháp → Đã xác nhận | Hủy",
        [
            "Tạo lệnh tháo dỡ sản phẩm (quyền Tạo)",
            "Khi Nháp + quyền Sửa: <b>Thêm dòng thu hồi</b> nguyên phụ liệu / bán thành phẩm",
            "Khi Nháp + quyền Sửa: <b>Xác nhận</b> (có thể sinh phiếu nguyên phụ liệu thừa)",
        ],
    )

    story.append(PageBreak())

    # ========== 6. QC ==========
    story.append(P("6. Chất lượng", styles["H1VN"]))
    story.append(
        P(
            "Hub: <b>/san-xuat/chat-luong/</b> — xem chỉ số nhanh và liên kết các màn vận hành / tiêu chuẩn.",
            styles["BodyVN"],
        )
    )

    screen_block(
        story,
        styles,
        "Yêu cầu kiểm tra chất lượng",
        "/san-xuat/chat-luong/yeu-cau/<mã>/",
        "Thường ở trạng thái Mở khi tạo",
        [
            "Tạo thủ công (quyền Tạo) hoặc tạo từ thống kê sản xuất đã xác nhận",
            "Màn chi tiết chủ yếu <b>xem</b> — không có nút đổi trạng thái riêng trên chi tiết yêu cầu",
            "Tiếp theo: tạo / hoàn tất <b>Phiếu kiểm tra</b>",
        ],
    )
    screen_block(
        story,
        styles,
        "Phiếu kiểm tra",
        "/san-xuat/chat-luong/phieu/<mã>/",
        "Chưa hoàn tất → Đã hoàn tất · Kết quả: Chờ / Đạt / Không đạt",
        [
            "Tạo phiếu (quyền Tạo): gắn yêu cầu / lệnh, nhập mẫu, tiêu chí, lỗi",
            "Khi chưa chốt + quyền Sửa: nhập tiêu chí / lỗi rồi <b>Chốt kết quả</b> (finalize)",
            "Nếu Không đạt: hệ thống có thể tạo cảnh báo chất lượng",
        ],
        "Nên chỉ nhập thành phẩm khi kết quả kiểm tra Đạt (theo quy trình vận hành).",
    )
    screen_block(
        story,
        styles,
        "Cảnh báo chất lượng",
        "/san-xuat/chat-luong/canh-bao/<mã>/",
        "Mở → Đã xử lý → Đóng",
        [
            "Xem danh sách / chi tiết (cảnh báo tỷ lệ lỗi hoặc phiếu không đạt)",
            "Khi Mở + quyền Sửa: <b>Ghi nhận xử lý</b> (ack)",
        ],
    )
    story.append(P("6.1. Danh mục tiêu chuẩn chất lượng", styles["H2VN"]))
    story.append(
        P(
            "Các màn tiêu chí, nhóm tiêu chí, chọn mẫu, bộ tiêu chuẩn, lỗi, nhóm lỗi: "
            "chỉ <b>Xem danh sách</b> + <b>Thêm</b> (quyền Tạo). Không có vòng đời duyệt.",
            styles["BodyVN"],
        )
    )
    story.append(
        P(
            "Ví dụ đường dẫn: /san-xuat/chat-luong/tieu-chi/ · /nhom-tieu-chi/ · /chon-mau/ · "
            "/bo-tieu-chuan/ · /loi/ · /nhom-loi/",
            styles["BulletVN"],
        )
    )

    # ========== 7. PHASE 3 ==========
    story.append(P("7. Đóng gói, truy xuất, giao việc, năng lực, xưởng, gia công", styles["H1VN"]))

    screen_block(
        story,
        styles,
        "Đóng gói",
        "/san-xuat/dong-goi/<mã>/",
        "Nháp → Đã xác nhận",
        [
            "Tạo phiếu đóng gói (quyền Tạo): gắn lệnh / yêu cầu nhập thành phẩm, size, màu, số thùng",
            "Khi Nháp + quyền Sửa: <b>Xác nhận đóng gói</b> → sinh mã lô",
            "Liên kết sang Tra cứu truy xuất theo mã lô",
        ],
    )
    screen_block(
        story,
        styles,
        "Truy xuất nguồn gốc",
        "/san-xuat/truy-xuat/",
        None,
        [
            "Nhập mã lệnh sản xuất, mã lô hoặc mã liên quan rồi tìm kiếm",
            "Xem timeline: kế hoạch → xuất nguyên phụ liệu → thống kê → kiểm tra → nhập thành phẩm → đóng gói",
            "<b>Không</b> có thao tác ghi dữ liệu (chỉ tra cứu)",
        ],
    )
    screen_block(
        story,
        styles,
        "Giao việc",
        "/san-xuat/giao-viec/",
        "Đang giao → Hoàn thành | Hủy",
        [
            "Tạo giao việc (quyền Tạo): lệnh, tổ/chuyền, công đoạn, người nhận, hạn",
            "Trên danh sách + quyền Sửa: <b>Hoàn thành</b> giao việc",
            "Có thể tùy chọn tạo việc sang module Công việc",
        ],
    )
    screen_block(
        story,
        styles,
        "Năng lực tổ / chuyền",
        "/san-xuat/nang-luc/",
        None,
        [
            "Lọc theo tháng / khoảng ngày, mã, tên tổ",
            "Xem năng lực kỳ, tải %, sản lượng đạt, tận dụng %",
            "Nút <b>Thêm tổ/chuyền</b> (quyền Tạo) — khai báo công suất/ngày",
            "Không sửa trực tiếp trên bảng tải kỳ",
        ],
    )
    screen_block(
        story,
        styles,
        "Xưởng (xác nhận tại chỗ)",
        "/san-xuat/shop-floor/",
        None,
        [
            "Xem lệnh Đã phát hành / Đang sản xuất",
            "Quyền Sửa: quét / nhập mã lệnh → xác nhận nhanh số lượng đạt, công đoạn, tổ "
            "(tạo hoặc cập nhật thống kê sản xuất)",
        ],
    )
    screen_block(
        story,
        styles,
        "Thuê gia công",
        "/san-xuat/thue-gia-cong/<mã>/",
        "Nháp → Đã gửi gia công → Đã nhận lại → Hoàn thành | Hủy",
        [
            "Tạo đơn thuê gia công (quyền Tạo)",
            "Quyền Sửa: <b>Thêm dòng xuất đi</b> gia công",
            "Quyền Sửa: <b>Ghi nhận nhận lại</b> (+ dòng nhận về nếu cần)",
            "Quyền Sửa: chuyển trạng thái <b>Gửi gia công</b> / <b>Hoàn thành</b> / <b>Hủy</b>",
        ],
    )

    story.append(PageBreak())

    # ========== 8. GIÁ THÀNH ==========
    story.append(P("8. Giá thành (tóm tắt thao tác)", styles["H1VN"]))
    story.append(
        P(
            "Hub: <b>/san-xuat/gia-thanh/</b> — điều hướng định mức, theo đơn, thực tế.",
            styles["BodyVN"],
        )
    )
    cost_rows = [
        [P("<b>Màn hình</b>", h), P("<b>Đường dẫn</b>", h), P("<b>Thao tác chính</b>", h)],
        [
            P("Giá thành live từ BOM", c),
            P("/san-xuat/gia-thanh/dinh-muc/", c),
            P("Xem / mở hồ sơ — không chốt kỳ", c),
        ],
        [
            P("Bảng giá thành định mức", c),
            P("/san-xuat/gia-thanh/dinh-muc/bang/", c),
            P("Tạo bảng (Tạo); khi Nháp: Tính lại · Chốt (Sửa)", c),
        ],
        [
            P("Giá thành kế hoạch theo đơn", c),
            P("/san-xuat/gia-thanh/theo-don/", c),
            P("Tạo; khi Nháp: Tính lại · Lưu chi phí thêm · Chốt; Xuất Excel", c),
        ],
        [
            P("Loại chi phí thêm", c),
            P("/san-xuat/gia-thanh/loai-chi-phi/", c),
            P("Xem · Thêm · Sửa loại chi phí", c),
        ],
        [
            P("Giá thành thực tế theo lệnh", c),
            P("/san-xuat/gia-thanh/thuc-te/ · …/lsx/<mã>/", c),
            P("Xem; quyền Sửa: Tính lại · Chốt kỳ", c),
        ],
    ]
    story.append(_table(cost_rows, [4.2 * cm, 5.5 * cm, 6.3 * cm]))

    story.append(P("8.1. Một số màn vận hành khác", styles["H2VN"]))
    other_rows = [
        [P("<b>Màn hình</b>", h), P("<b>Đường dẫn</b>", h), P("<b>Thao tác</b>", h)],
        [
            P("Báo cáo vận hành", c),
            P("/san-xuat/bao-cao-van-hanh/", c),
            P("Lọc kỳ / sản phẩm / công đoạn · Xuất CSV — chỉ xem", c),
        ],
        [
            P("Dừng chuyền", c),
            P("/san-xuat/dung-chuyen/", c),
            P("Ghi nhận dừng chuyền (quyền Tạo)", c),
        ],
        [
            P("Phiếu xử lý hàng không đạt", c),
            P("/san-xuat/ncr/", c),
            P("Xem; khi Nháp + Sửa: Xác nhận", c),
        ],
        [
            P("Lương sản phẩm", c),
            P("/san-xuat/luong-san-pham/", c),
            P("Xem báo cáo · Xuất nhân sự · Map tổ–nhân sự", c),
        ],
        [
            P("Vị trí staging", c),
            P("/san-xuat/staging/", c),
            P("Cập nhật loại vị trí (quyền Sửa)", c),
        ],
    ]
    story.append(_table(other_rows, [4.2 * cm, 5.5 * cm, 6.3 * cm]))

    # ========== 9. THIẾT LẬP CHUNG ==========
    story.append(PageBreak())
    story.append(P("9. Thiết lập chung — hướng dẫn cấu hình", styles["H1VN"]))
    story.append(
        P(
            "Màn <b>Sản xuất → Thiết lập chung</b> (đường dẫn "
            "<font face=\"VN-B\">/san-xuat/thiet-lap/</font>) lưu cấu hình vận hành trên hệ thống. "
            "Giá trị trong database <b>ưu tiên hơn</b> biến môi trường; bấm <b>Lưu thiết lập</b> "
            "là có hiệu lực ngay (không cần deploy lại).",
            styles["BodyVN"],
        )
    )
    story.append(P("9.1. Quyền & cách mở", styles["H2VN"]))
    story.append(
        P(
            "• Cần quyền <b>Xem</b> module Sản xuất để mở trang; quyền <b>Sửa</b> để lưu. "
            "Không có quyền Sửa thì chỉ xem được cấu hình hiện tại.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Menu sidebar: nhóm <b>Sản xuất</b> → mục cuối <b>Thiết lập chung</b> (icon bánh răng).",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Giao diện chia mục: Cổng quy trình · Chất lượng · Năng lực · Kho & tích hợp · "
            "Shop floor · Mã chứng từ. Thanh <b>Lưu thiết lập</b> dính đáy trang.",
            styles["BulletVN"],
        )
    )

    story.append(P("9.2. Ba mức cổng quy trình", styles["H2VN"]))
    story.append(
        P(
            "Mỗi cổng kiểm tra thứ tự bước trước khi cho phép thao tác tiếp theo:",
            styles["BodyVN"],
        )
    )
    gate_mode_rows = [
        [P("<b>Mức</b>", h), P("<b>Ý nghĩa</b>", h), P("<b>Khi nào dùng</b>", h)],
        [
            P("<b>Chặn</b>", c),
            P("Không cho tiếp tục nếu thiếu bước trước", c),
            P("Vận hành chuẩn / truy xuất nghiêm", c),
        ],
        [
            P("<b>Cảnh báo</b>", c),
            P("Cho phép nhưng nhắc trên màn hình", c),
            P("Pilot / giai chuyển quy trình", c),
        ],
        [
            P("<b>Tắt</b>", c),
            P("Không kiểm tra cổng này", c),
            P("Chỉ khi chủ động nới lỏng tạm thời", c),
        ],
    ]
    story.append(_table(gate_mode_rows, [3.2 * cm, 6.5 * cm, 6.3 * cm]))

    story.append(P("9.3. Các cổng đang cấu hình được", styles["H2VN"]))
    gate_rows = [
        [P("<b>Cổng</b>", h), P("<b>Mặc định</b>", h), P("<b>Ảnh hưởng</b>", h)],
        [
            P("Phát hành lệnh → tạo yêu cầu xuất vật tư", c),
            P("Chặn", c),
            P("Lệnh nháp không tạo được yêu cầu xuất", c),
        ],
        [
            P("Xuất kho đã ghi sổ → xác nhận thống kê", c),
            P("Chặn", c),
            P("Chưa duyệt xuất thì không chốt thống kê", c),
        ],
        [
            P("Thống kê đã xác nhận → nhập thành phẩm", c),
            P("Chặn", c),
            P("Không tạo yêu cầu nhập TP nếu chưa có thống kê", c),
        ],
        [
            P("Phiếu kiểm tra Đạt → nhập thành phẩm", c),
            P("Chặn", c),
            P("Bắt buộc QC Đạt trước khi nhập TP", c),
        ],
        [
            P("Cảnh báo chất lượng đang mở → nhập TP", c),
            P("Chặn", c),
            P("Còn cảnh báo mở thì không nhập TP", c),
        ],
        [
            P("Đóng gói đã xác nhận → hoàn thành lệnh", c),
            P("Tắt", c),
            P("Bật Chặn khi muốn bắt buộc có phiếu đóng gói trước Done", c),
        ],
    ]
    story.append(_table(gate_rows, [6.8 * cm, 2.2 * cm, 7.0 * cm]))

    story.append(P("9.4. Chất lượng & truy xuất", styles["H2VN"]))
    qc_set_rows = [
        [P("<b>Thiết lập</b>", h), P("<b>Mặc định</b>", h), P("<b>Ghi chú</b>", h)],
        [
            P("Tự tạo yêu cầu kiểm tra khi xác nhận thống kê", c),
            P("Bật", c),
            P("Tắt nếu muốn tạo yêu cầu kiểm tra thủ công", c),
        ],
        [
            P("Tự tạo cảnh báo khi tỷ lệ lỗi vượt ngưỡng", c),
            P("Bật", c),
            P("Tắt khi chạy thử để giảm “ồn” cảnh báo", c),
        ],
        [
            P("Dung sai tỷ lệ lỗi mặc định (%)", c),
            P("5", c),
            P("Dùng khi sản phẩm chưa gắn bộ tiêu chuẩn QC", c),
        ],
        [
            P("Số lượng mẫu mặc định", c),
            P("5", c),
            P("Khi chưa chọn phương pháp lấy mẫu", c),
        ],
        [
            P("Ngưỡng sự kiện timeline (Truy xuất)", c),
            P("4", c),
            P("Nút «Thiếu bước nào?» gợi ý nếu timeline ngắn hơn ngưỡng", c),
        ],
    ]
    story.append(_table(qc_set_rows, [7.0 * cm, 2.0 * cm, 7.0 * cm]))

    story.append(P("9.5. Năng lực, danh sách & OEE", styles["H2VN"]))
    cap_rows = [
        [P("<b>Thiết lập</b>", h), P("<b>Mặc định</b>", h), P("<b>Ghi chú</b>", h)],
        [
            P("Ngưỡng cảnh báo / quá tải năng lực (%)", c),
            P("80 / 100", c),
            P("Màu vàng / đỏ trên màn Năng lực SX", c),
        ],
        [
            P("Số ngày lọc danh sách mặc định", c),
            P("7", c),
            P("Khoảng ngày khi mở danh sách lệnh, thống kê…", c),
        ],
        [
            P("Số giờ / ca (OEE)", c),
            P("8", c),
            P("Tính sẵn sàng trên màn Dừng chuyền / OEE", c),
        ],
    ]
    story.append(_table(cap_rows, [7.0 * cm, 2.5 * cm, 6.5 * cm]))

    story.append(P("9.6. Kho, tích hợp & shop floor", styles["H2VN"]))
    stock_rows = [
        [P("<b>Thiết lập</b>", h), P("<b>Mặc định</b>", h), P("<b>Ghi chú</b>", h)],
        [
            P("Giữ chỗ tồn khi tạo yêu cầu xuất", c),
            P("Bật", c),
            P("Tắt khi soft-launch / không muốn khóa tồn", c),
        ],
        [
            P("Bắt buộc liên kết phiếu nhập KiotViet để hoàn tất nhập TP", c),
            P("Bật", c),
            P("Tắt = có thể đánh dấu xong không cần phiếu KV", c),
        ],
        [
            P("Hiện banner hàng đợi duyệt xuất vật tư", c),
            P("Bật", c),
            P("Banner trên hub Điều phối khi còn yêu cầu chờ duyệt", c),
        ],
        [
            P("Shop floor: quét xong tự xác nhận thống kê", c),
            P("Bật", c),
            P("Tắt = chỉ tạo thống kê nháp khi quét", c),
        ],
        [
            P("Shop floor: số lượng đạt mặc định mỗi lần quét", c),
            P("1", c),
            P("SL đạt điền sẵn trên màn xác nhận xưởng", c),
        ],
    ]
    story.append(_table(stock_rows, [7.2 * cm, 2.0 * cm, 6.8 * cm]))

    story.append(P("9.7. Mã chứng từ (prefix)", styles["H2VN"]))
    story.append(
        P(
            "Mỗi loại chứng từ có prefix riêng (ví dụ lệnh sản xuất = <b>LSX</b> → mã dạng "
            "LSX-2026-0001). Đổi prefix chỉ ảnh hưởng <b>mã sinh mới</b> sau khi lưu; "
            "chứng từ cũ giữ nguyên. Chỉ dùng chữ in hoa, số và dấu gạch ngang.",
            styles["BodyVN"],
        )
    )
    prefix_rows = [
        [P("<b>Nhóm</b>", h), P("<b>Prefix mặc định (ví dụ)</b>", h)],
        [
            P("Điều phối", c),
            P("LSX · YCX · TKSX · YCNTP · BG · TRABTP · LTD · NPLT", c),
        ],
        [
            P("Chất lượng", c),
            P("YCKT · PKT · CBQC · NCR", c),
        ],
        [
            P("Kế hoạch / mua", c),
            P("KHTT · KHNVL · KHCT · YCM · DMH", c),
        ],
        [
            P("Xưởng / đóng gói / giá thành", c),
            P("GV · DG · GC · GTDM · GTDH · GTT · DT", c),
        ],
    ]
    story.append(_table(prefix_rows, [5.0 * cm, 11.0 * cm]))

    story.append(P("9.8. Gợi ý cấu hình cơ bản (khuyến nghị)", styles["H2VN"]))
    story.append(
        P(
            "• Vận hành chuẩn: mọi cổng (trừ đóng gói) = <b>Chặn</b>; tự tạo yêu cầu kiểm tra "
            "và cảnh báo lỗi = <b>Bật</b>; giữ chỗ tồn + bắt buộc link KiotViet = <b>Bật</b>.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Pilot / chạy thử: một số cổng đổi sang <b>Cảnh báo</b> hoặc <b>Tắt</b>; "
            "có thể tắt tự tạo cảnh báo lỗi để giảm nhiễu.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Không đưa vào Thiết lập chung (đã có màn riêng): BOM / hồ sơ, tổ-chuyền năng lực, "
            "catalog tiêu chuẩn QC, staging, map tổ–nhân sự, credential KiotViet.",
            styles["BulletVN"],
        )
    )

    # ========== 10. CHECKLIST ==========
    story.append(P("10. Checklist thao tác theo thứ tự", styles["H1VN"]))
    story.append(
        P(
            "Làm lần lượt; mỗi bước cần đúng quyền và trạng thái chứng từ trước đó đã xong. "
            "Cổng trên Thiết lập chung có thể chặn nếu bỏ qua bước.",
            styles["BodyVN"],
        )
    )
    check_rows = [
        [P("<b>#</b>", h), P("<b>Việc cần làm</b>", h), P("<b>Màn hình / nút chính</b>", h), P("<b>Kết quả</b>", h)],
        [
            P("1", c),
            P("Đủ định mức BOM + tồn nguyên phụ liệu + tổ/chuyền", c),
            P("Hồ sơ · Kho NPL · Năng lực", c),
            P("Đủ điều kiện mở lệnh", c),
        ],
        [
            P("2", c),
            P("Tạo & xác nhận kế hoạch tổng thể", c),
            P("Kế hoạch tổng thể → Xác nhận", c),
            P("Trạng thái Đã xác nhận", c),
        ],
        [
            P("3", c),
            P("Tách & xác nhận kế hoạch nguyên phụ liệu; mua nếu thiếu", c),
            P("Kế hoạch NPL → Xác nhận · Yêu cầu mua · Đơn mua", c),
            P("NPL đủ hoặc đã đặt mua", c),
        ],
        [
            P("4", c),
            P("Tách & xác nhận kế hoạch chi tiết; sinh lệnh (nếu dùng)", c),
            P("Kế hoạch chi tiết → Xác nhận → Sinh lệnh", c),
            P("Có lệnh hoặc sẵn sàng tạo lệnh", c),
        ],
        [
            P("5", c),
            P("Tạo lệnh sản xuất → Phát hành", c),
            P("Lệnh sản xuất → Phát hành", c),
            P("Lệnh Đã phát hành", c),
        ],
        [
            P("6", c),
            P("Tạo yêu cầu xuất → Duyệt xuất kho", c),
            P("Từ lệnh → Yêu cầu xuất → Duyệt", c),
            P("Phiếu xuất đã ghi sổ", c),
        ],
        [
            P("7", c),
            P("Ghi thống kê theo công đoạn → Xác nhận", c),
            P("Thống kê sản xuất hoặc Xưởng", c),
            P("Có sản lượng trên lệnh", c),
        ],
        [
            P("8", c),
            P("Tạo yêu cầu kiểm tra → Chốt phiếu kiểm tra Đạt", c),
            P("Chất lượng — yêu cầu / phiếu", c),
            P("Kết quả Đạt", c),
        ],
        [
            P("9", c),
            P("Tạo yêu cầu nhập thành phẩm → Gửi → Liên kết KiotViet", c),
            P("Yêu cầu nhập thành phẩm", c),
            P("Thành phẩm vào kho", c),
        ],
        [
            P("10", c),
            P("Xác nhận đóng gói → kiểm tra truy xuất", c),
            P("Đóng gói · Truy xuất", c),
            P("Có mã lô + timeline đủ", c),
        ],
    ]
    story.append(_table(check_rows, [0.9 * cm, 5.2 * cm, 5.2 * cm, 4.7 * cm]))

    # ========== 11. GHI CHÚ ==========
    story.append(P("11. Ghi chú kỹ thuật", styles["H1VN"]))
    story.append(
        P(
            "• Luồng kiểm thử end-to-end nằm trong file "
            "<font face=\"VN-B\">san_xuat/scripts/full_workflow_check.py</font> "
            "(các bước từ kế hoạch tổng thể đến truy xuất).",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Nguồn sự thật dữ liệu gốc: Thành phẩm → KiotViet · Nguyên phụ liệu → Kho NPL · "
            "Định mức BOM / quy trình / giá thành → Hồ sơ sản xuất.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Cấu hình vận hành: model <font face=\"VN-B\">SxGeneralSettings</font> "
            "(singleton) · đọc qua <font face=\"VN-B\">san_xuat/services/sx_settings.py</font> · "
            "UI <font face=\"VN-B\">/san-xuat/thiet-lap/</font>.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Khi giao diện đổi nhãn nút hoặc tên menu, ưu tiên đối chiếu <b>đường dẫn URL</b> "
            "trong module Sản xuất (file urls.py) và quyền Xem / Tạo / Sửa của tài khoản.",
            styles["BulletVN"],
        )
    )
    story.append(
        P(
            "• Tài liệu này mô tả thao tác được phép theo mã nguồn hiện tại; "
            "chính sách nội bộ công ty có thể yêu cầu thêm bước phê duyệt giấy tờ ngoài hệ thống.",
            styles["BulletVN"],
        )
    )

    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceBefore=4, spaceAfter=8))
    story.append(P("— Hết tài liệu —", styles["SmallVN"]))
    story.append(P("Portal JustPlay · Module Sản xuất · Bản chi tiết thao tác màn hình + thiết lập chung", styles["SmallVN"]))

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.6 * cm,
        title="Quy trình sản xuất chi tiết — Portal JustPlay",
        author="Portal JustPlay",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"OK: {OUT}")
    print(f"Size: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    build()
