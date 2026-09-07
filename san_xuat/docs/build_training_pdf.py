"""PDF training ngắn — khớp menu Portal + nhúng ảnh diagram tách riêng."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
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

from render_training_diagrams import main as render_diagrams

pdfmetrics.registerFont(TTFont("VN", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("VN-B", r"C:\Windows\Fonts\arialbd.ttf"))

HERE = Path(__file__).resolve().parent
OUT = HERE / "Quy_trinh_san_xuat_PortalJustPlay.pdf"
DIAG1 = HERE / "diagrams" / "01-luong-portal.png"
DIAG2 = HERE / "diagrams" / "02-buoc-xuong.png"

PRIMARY = HexColor("#dc2626")
ACCENT = HexColor("#b91c1c")
LIGHT = HexColor("#fef2f2")
BORDER = HexColor("#fecaca")
MUTED = HexColor("#64748b")
DARK = HexColor("#0f172a")


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Cover", fontName="VN-B", fontSize=20, leading=26, textColor=PRIMARY, alignment=TA_CENTER, spaceAfter=8))
    s.add(ParagraphStyle("Sub", fontName="VN", fontSize=11, leading=15, textColor=MUTED, alignment=TA_CENTER, spaceAfter=4))
    s.add(ParagraphStyle("H1VN", fontName="VN-B", fontSize=13, leading=17, textColor=PRIMARY, spaceBefore=12, spaceAfter=6))
    s.add(ParagraphStyle("H2VN", fontName="VN-B", fontSize=11, leading=14, textColor=HexColor("#991b1b"), spaceBefore=8, spaceAfter=4))
    s.add(ParagraphStyle("Body", fontName="VN", fontSize=9.5, leading=13, textColor=DARK, alignment=TA_LEFT, spaceAfter=5))
    s.add(ParagraphStyle("BulletVN", fontName="VN", fontSize=9, leading=12.5, textColor=DARK, leftIndent=10, spaceAfter=2))
    s.add(ParagraphStyle("Small", fontName="VN", fontSize=8, leading=10.5, textColor=MUTED, alignment=TA_CENTER))
    s.add(ParagraphStyle("Cell", fontName="VN", fontSize=8, leading=10.5, textColor=DARK))
    s.add(ParagraphStyle("Head", fontName="VN-B", fontSize=8, leading=10.5, textColor=white))
    s.add(ParagraphStyle("Cap", fontName="VN", fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=8))
    return s


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(1.1)
    canvas.line(1.6 * cm, A4[1] - 1.1 * cm, A4[0] - 1.6 * cm, A4[1] - 1.1 * cm)
    canvas.setFont("VN", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.6 * cm, A4[1] - 0.9 * cm, "Portal JustPlay — Sản xuất (menu đang mở)")
    canvas.drawRightString(A4[0] - 1.6 * cm, A4[1] - 0.9 * cm, "Training nhân viên")
    canvas.line(1.6 * cm, 1.15 * cm, A4[0] - 1.6 * cm, 1.15 * cm)
    canvas.drawCentredString(A4[0] / 2, 0.7 * cm, f"Trang {doc.page}")
    canvas.restoreState()


def P(text, st):
    return Paragraph(text, st)


def table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("BOX", (0, 0), (-1, -1), 0.7, PRIMARY),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT])]
    t.setStyle(TableStyle(cmds))
    return t


def fit_image(path: Path, max_w, max_h):
    from PIL import Image as PILImage

    with PILImage.open(path) as im:
        w, h = im.size
    ratio = min(max_w / w, max_h / h)
    return Image(str(path), width=w * ratio, height=h * ratio)


def build():
    render_diagrams()
    st = styles()
    c, h = st["Cell"], st["Head"]
    story = []

    story.append(Spacer(1, 1.6 * cm))
    story.append(P("PORTAL JUSTPLAY", st["Sub"]))
    story.append(P("Quy trình sản xuất trên Portal", st["Cover"]))
    story.append(P("Theo menu và nút đang mở cho nhân viên — không theo tài liệu thiết kế cũ", st["Sub"]))
    story.append(HRFlowable(width="80%", thickness=2, color=ACCENT, spaceBefore=6, spaceAfter=8, hAlign="CENTER"))
    story.append(P("07/09/2026 · v5.1  ·  Có hướng dẫn từng màn  ·  Ảnh: san_xuat/docs/diagrams/", st["Small"]))
    story.append(Spacer(1, 0.5 * cm))

    info = [
        [P("<b>Luồng chính</b>", c), P("Hồ sơ → Đơn đặt hàng → Kế hoạch sản xuất (Chuyển SX) → Phân công SX → Điều phối / QC → Kho sản phẩm", c)],
        [P("<b>Ảnh riêng</b>", c), P("01-luong-portal.png  ·  02-buoc-xuong.png", c)],
        [P("<b>Không train như bước bắt buộc</b>", c), P("Đóng gói, shop floor, giá thành, kế hoạch tổng thể / chi tiết, thống kê sản xuất (đã ẩn khỏi menu)", c)],
    ]
    t = Table(info, colWidths=[4.2 * cm, 11.8 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 1, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    story.append(P("1. Menu đang mở trên Portal", st["H1VN"]))
    menu_rows = [
        [P("<b>#</b>", h), P("<b>Menu</b>", h), P("<b>Màn nhân viên vào</b>", h)],
        [P("1", c), P("Hồ sơ", c), P("Hồ sơ thiết kế sản phẩm (BOM + quy trình) · Duyệt công đoạn", c)],
        [P("2", c), P("Đơn đặt hàng", c), P("Danh sách · Lên đơn đặt hàng · Xác nhận đơn đặt hàng", c)],
        [P("3", c), P("Kế hoạch SX", c), P("Kế hoạch sản xuất (Hàng đợi / Đã chuyển SX / Lộ trình) · Thời gian trung gian · Kế hoạch NPL · Yêu cầu mua NPL", c)],
        [P("4", c), P("Kho NPL", c), P("Tồn · phiếu nhập · phiếu xuất", c)],
        [P("5", c), P("Điều phối", c), P("Lệnh sản xuất · Yêu cầu xuất vật tư · Tình hình bàn giao · Yêu cầu nhập thành phẩm", c)],
        [P("6", c), P("Phân công SX", c), P("Tiến độ hàng hoá · Tổ cắt / in ép / thêu / may / ủi gấp xếp / giao hàng · Thuê gia công", c)],
        [P("7", c), P("Kiểm tra chất lượng", c), P("Tiến độ QC · Phiếu kiểm tra · Cảnh báo · Hàng không đạt · Tiêu chuẩn", c)],
        [P("8", c), P("Kho sản phẩm", c), P("Tồn / phiếu nhập thành phẩm", c)],
        [P("9", c), P("Báo cáo", c), P("Truy xuất nguồn gốc · Báo cáo vận hành", c)],
    ]
    story.append(table(menu_rows, [1.2 * cm, 3.6 * cm, 11.2 * cm]))

    story.append(PageBreak())
    story.append(P("2. Sơ đồ luồng Portal", st["H1VN"]))
    story.append(P(
        "Xác nhận đơn chỉ đưa đơn vào tab <b>Hàng đợi</b>. Lệnh chỉ sinh khi bấm <b>Chuyển SX</b> "
        "(modal chọn BOM &amp; công đoạn). Lệnh được phát hành và đẩy sang <b>Phân công SX</b>.",
        st["Body"],
    ))
    story.append(fit_image(DIAG1, 16.5 * cm, 21 * cm))
    story.append(P("File ảnh: san_xuat/docs/diagrams/01-luong-portal.png", st["Cap"]))

    story.append(P("3. Thao tác từng bước (tên nút trên màn)", st["H1VN"]))
    steps = [
        ("Hồ sơ", "Sản xuất → Hồ sơ → Hồ sơ thiết kế sản phẩm", "Có BOM đang dùng và quy trình / routing đã duyệt."),
        ("Lên đơn", "Đơn đặt hàng → Lên đơn đặt hàng", "Chọn SP, số lượng, BOM. Lưu nháp."),
        ("Xác nhận", "Đơn đặt hàng → Xác nhận đơn đặt hàng", "Đơn vào tab Hàng đợi. Chưa có lệnh."),
        ("Chuyển SX", "Kế hoạch SX → Kế hoạch sản xuất → tab Hàng đợi → nút Chuyển SX", "Chọn BOM &amp; công đoạn trong modal. Sinh lệnh + đẩy tổ."),
        ("Lộ trình", "Cùng màn, tab Lộ trình", "Kéo lịch theo tổ nếu cần xếp ngày."),
        ("Nhận việc", "Phân công SX → tổ của mình → Nhận sản xuất", "Kế hoạch / lệnh sang Đang sản xuất."),
        ("Làm hàng", "Cùng phiếu tổ", "Phân công nhân viên → ghi tiến độ → Hoàn thành (chỉ khóa tổ đó)."),
        ("Xuất NPL", "Điều phối → Yêu cầu xuất vật tư → duyệt", "Sinh phiếu xuất trên Kho NPL."),
        ("QC", "Kiểm tra chất lượng → Phiếu kiểm tra", "Chốt Đạt theo tab tổ. Đóng cảnh báo trước khi nhập TP."),
        ("Nhập TP", "Điều phối → Yêu cầu nhập thành phẩm", "Kho sản phẩm nhận hàng. Tra cứu ở Báo cáo → Truy xuất."),
    ]
    step_rows = [[P("<b>Bước</b>", h), P("<b>Vào đâu / bấm gì</b>", h), P("<b>Kết quả</b>", h)]]
    for a, b, d in steps:
        step_rows.append([P(a, c), P(b, c), P(d, c)])
    story.append(table(step_rows, [3.0 * cm, 6.6 * cm, 6.4 * cm]))

    story.append(PageBreak())
    story.append(P("4. Sơ đồ các bước trên xưởng", st["H1VN"]))
    story.append(P(
        "Đúng 6 mục trong menu <b>Phân công SX</b>. Tổ sau không bị hệ thống chặn vì tổ trước chưa Hoàn thành.",
        st["Body"],
    ))
    story.append(fit_image(DIAG2, 16.8 * cm, 12.2 * cm))
    story.append(P("File ảnh: san_xuat/docs/diagrams/02-buoc-xuong.png", st["Cap"]))

    story.append(P("5. Ai bấm nút nào", st["H1VN"]))
    role_rows = [
        [P("<b>Vai trò</b>", h), P("<b>Menu</b>", h), P("<b>Nút chính</b>", h)],
        [P("Lên đơn", c), P("Đơn đặt hàng → Lên đơn", c), P("Lưu đơn nháp", c)],
        [P("Duyệt đơn", c), P("Đơn đặt hàng → Xác nhận", c), P("Xác nhận", c)],
        [P("Kế hoạch", c), P("Kế hoạch sản xuất", c), P("Chuyển SX · tab Lộ trình", c)],
        [P("Tổ trưởng", c), P("Phân công SX → tổ mình", c), P("Nhận sản xuất · Phân công · Hoàn thành", c)],
        [P("Điều phối", c), P("Điều phối", c), P("Yêu cầu xuất vật tư · Yêu cầu nhập TP", c)],
        [P("Kho NPL", c), P("Kho NPL", c), P("Phiếu xuất sau YCX đã duyệt", c)],
        [P("QC", c), P("Kiểm tra chất lượng", c), P("Phiếu kiểm tra · Cảnh báo", c)],
        [P("Kho TP", c), P("Kho sản phẩm", c), P("Nhận thành phẩm", c)],
    ]
    story.append(table(role_rows, [3.2 * cm, 6.4 * cm, 6.4 * cm]))

    story.append(P("6. Checklist 1 đơn mẫu", st["H1VN"]))
    chk = [
        [P("<b>#</b>", h), P("<b>Việc</b>", h), P("<b>Menu / nút</b>", h)],
        [P("1", c), P("Có hồ sơ BOM + quy trình duyệt", c), P("Hồ sơ", c)],
        [P("2", c), P("Lên đơn → Xác nhận", c), P("Đơn đặt hàng", c)],
        [P("3", c), P("Tab Hàng đợi → Chuyển SX", c), P("Kế hoạch sản xuất", c)],
        [P("4", c), P("Tổ cắt: Nhận sản xuất → Phân công → Hoàn thành", c), P("Phân công SX", c)],
        [P("5", c), P("Lần lượt In ép / Thêu / May / Ủi / Giao hàng", c), P("Phân công SX", c)],
        [P("6", c), P("Tạo và duyệt Yêu cầu xuất vật tư", c), P("Điều phối + Kho NPL", c)],
        [P("7", c), P("Phiếu kiểm tra theo tổ, chốt Đạt", c), P("Kiểm tra chất lượng", c)],
        [P("8", c), P("Yêu cầu nhập thành phẩm", c), P("Điều phối", c)],
        [P("9", c), P("Kiểm tồn kho thành phẩm", c), P("Kho sản phẩm", c)],
        [P("10", c), P("Đối chiếu truy xuất nguồn gốc", c), P("Báo cáo", c)],
    ]
    story.append(table(chk, [1.0 * cm, 8.2 * cm, 6.8 * cm]))

    story.append(P("7. Việc hay kẹt", st["H1VN"]))
    err = [
        [P("<b>Hiện tượng</b>", h), P("<b>Vì sao trên Portal</b>", h), P("<b>Xử lý</b>", h)],
        [P("Không xác nhận đơn", c), P("Công đoạn / SMV trên đơn chưa đủ", c), P("Sửa hồ sơ / đơn nháp", c)],
        [P("Không Chuyển SX", c), P("Đơn chưa xác nhận hoặc thiếu quyền", c), P("Xác nhận đơn; cấp Kế hoạch SX", c)],
        [P("Modal thiếu hồ sơ", c), P("Mã SP chưa có BOM", c), P("Tạo hồ sơ thiết kế rồi mở lại", c)],
        [P("Tổ không thấy phiếu", c), P("Chưa Chuyển SX hoặc tổ không có trong quy trình", c), P("Tab Đã chuyển SX + quy trình đơn", c)],
        [P("Không xuất vật tư", c), P("Chưa Chuyển SX (lệnh chưa phát hành)", c), P("Chuyển SX trước", c)],
        [P("Không nhập thành phẩm", c), P("QC chưa Đạt / còn cảnh báo mở", c), P("Chốt phiếu QC, đóng cảnh báo", c)],
    ]
    story.append(table(err, [4.4 * cm, 6.2 * cm, 5.4 * cm]))

    story.append(PageBreak())
    story.append(P("8. Hướng dẫn từng màn hình", st["H1VN"]))
    story.append(P(
        "Chỉ màn đang mở trên menu. Làm theo đúng tên nút trên trang.",
        st["Body"],
    ))

    def screen(title, path, actions, note=None):
        rows = [[P("<b>Việc</b>", h), P("<b>Cách làm / nút</b>", h)]]
        for a, b in actions:
            rows.append([P(a, c), P(b, c)])
        parts = [
            P(title, st["H2VN"]),
            P(f"<b>Đường dẫn:</b> {path}", st["Body"]),
            table(rows, [5.2 * cm, 10.8 * cm]),
        ]
        if note:
            parts.append(P(note, st["Body"]))
        parts.append(Spacer(1, 0.15 * cm))
        for p in parts:
            story.append(p)

    screen(
        "8.1 Hồ sơ thiết kế sản phẩm",
        "/san-xuat/ho-so/  ·  chi tiết /ho-so/&lt;id&gt;/",
        [
            ("Tạo / mở hồ sơ", "Danh sách → Thêm, hoặc bấm dòng"),
            ("Chuẩn bị lên đơn", "Tab BOM (bản kích hoạt) + tab Quy trình (routing duyệt)"),
            ("Mã mới", "IE: Thư viện / Duyệt công đoạn trước khi xác nhận đơn"),
        ],
    )
    screen(
        "8.2 Lên đơn đặt hàng",
        "/san-xuat/don-hang/them/",
        [
            ("Đầu đơn", "Khách, ngày DK thực hiện, ngày DK hoàn thành"),
            ("Dòng hàng", "Chọn SP → BOM → routing gợi ý → nhập SL theo size"),
            ("Lưu", "Nút Lưu đơn → đơn còn Nháp"),
        ],
    )
    screen(
        "8.3 Xác nhận đơn / Chi tiết đơn",
        "/san-xuat/don-hang/xac-nhan/  ·  /don-hang/&lt;id&gt;/",
        [
            ("Duyệt hàng loạt", "Màn Xác nhận: nút Xác nhận hoặc Từ chối (+ lý do)"),
            ("Duyệt từng đơn", "Chi tiết: Xác nhận / Từ chối"),
            ("Sau xác nhận", "Đơn vào tab Hàng đợi. Không sửa routing. Link sang Kế hoạch"),
        ],
    )
    screen(
        "8.4 Kế hoạch sản xuất — Hàng đợi",
        "/san-xuat/ke-hoach/bang/?tab=queue",
        [
            ("Xếp việc", "Đổi ưu tiên trên dòng · Giữ / Bỏ giữ"),
            ("Chuyển SX", "Nút Chuyển SX → modal chọn BOM &amp; công đoạn → Chuyển SX"),
            ("Thiếu hồ sơ", "Trong modal: Tạo hồ sơ thiết kế, rồi mở lại"),
        ],
        "Tab Đã chuyển SX: nút Tiến độ. Tab Lộ trình: kéo lịch theo tổ.",
    )
    screen(
        "8.5 Thời gian trung gian · Kế hoạch NPL · Yêu cầu mua NPL",
        "/ke-hoach/thoi-gian-trung-gian/  ·  /ke-hoach/npl/  ·  /ke-hoach/yeu-cau-mua-npl/",
        [
            ("Thời gian trung gian", "Nhập phút kiểm đếm / vận chuyển giữa tổ → Lưu"),
            ("Kế hoạch NPL", "Tính kế hoạch → làm mới tồn → Xác nhận → tạo yêu cầu mua từ shortfall"),
            ("Yêu cầu mua", "Gửi duyệt → Duyệt yêu cầu mua → nhập trên Kho NPL"),
        ],
    )

    story.append(PageBreak())
    screen(
        "8.6 Chi tiết lệnh sản xuất",
        "/san-xuat/dieu-phoi/lenh-sx/&lt;id&gt;/",
        [
            ("Công cụ", "In A5 · Tiến độ · Truy vết"),
            ("Lệnh nháp (tạo tay)", "Lưu · Phát hành"),
            ("Lệnh từ Chuyển SX", "Thường đã phát hành. Tiếp theo: Xuất VT · Kiểm tra sản phẩm · nhập TP"),
            ("Khóa lệnh", "Hoàn thành khi checklist đủ 100%"),
        ],
    )
    screen(
        "8.7 Yêu cầu xuất vật tư",
        "/dieu-phoi/yeu-cau-xuat-vt/  hoặc nút Xuất VT trên lệnh",
        [
            ("Tạo", "Từ lệnh: Xuất VT / Tạo"),
            ("Duyệt", "Duyệt xuất đủ, hoặc duyệt một phần rồi Bổ sung xuất đủ"),
            ("Kho", "Sinh phiếu xuất Kho NPL đã ghi sổ · In A5 nếu cần giấy"),
        ],
    )
    screen(
        "8.8 Tình hình bàn giao · Nhập thành phẩm",
        "/dieu-phoi/tinh-hinh-ban-giao/  ·  /dieu-phoi/yeu-cau-nhap-tp/",
        [
            ("Bàn giao", "Xem SL gửi/nhận. Tạo phiếu từ khối bàn giao trên lệnh"),
            ("Nhập TP", "Tạo yêu cầu nhập thành phẩm · nhập SL theo size + kho"),
            ("Một phần", "Nút Tiếp tục khi chưa nhập hết"),
        ],
        "Nhập TP bị chặn nếu QC chưa Đạt hoặc còn cảnh báo mở.",
    )
    screen(
        "8.9 Phân công SX — Tiến độ hàng hoá",
        "/san-xuat/cong-viec-to/tien-do-hang-hoa/",
        [
            ("Xem", "Mọi lệnh × mọi tổ, lọc ưu tiên / hạn"),
            ("Không ghi SL ở đây", "Bấm lệnh/tổ để sang Quản lý tổ"),
        ],
    )
    screen(
        "8.10 Quản lý tổ (Cắt / In ép / Thêu / May / Ủi / Giao hàng)",
        "/san-xuat/cong-viec-to/&lt;slug&gt;/",
        [
            ("Nhận sản xuất", "Lần đầu — lệnh sang Đang sản xuất"),
            ("Phân công", "Từng công đoạn → chọn NV → Lưu phân công"),
            ("Ghi SL", "Mở phiếu Tiến độ tổ, gõ ô theo ngày"),
            ("Hoàn thành", "Khóa tổ này. Tổ sau không bị chặn"),
        ],
        "Thanh tổ: Công việc · Quản lý nhân sự · Tiến độ hàng hoá. GC đang mở thì không phân công nội bộ.",
    )

    story.append(PageBreak())
    screen(
        "8.11 Phiếu kiểm tra / Tiến độ QC",
        "/chat-luong/  ·  /chat-luong/phieu/",
        [
            ("Tiến độ QC", "Xem lệnh/tổ đã kiểm chưa"),
            ("Làm phiếu", "Tab theo tổ → nhập tiêu chí → Lưu tổ … → hết tổ thì Chốt phiếu"),
            ("Cảnh báo / NCR", "Đóng cảnh báo; xử lý hàng không đạt trước nhập TP"),
        ],
    )
    screen(
        "8.12 Kho sản phẩm · Truy xuất · Tổng quan",
        "/kho-san-pham/  ·  /san-xuat/truy-xuat/  ·  /san-xuat/tong-quan/",
        [
            ("Kho sản phẩm", "Xem tồn / phiếu nhập sau khi đã nhận YCNTP"),
            ("Truy xuất", "Gõ mã đơn / lệnh / lô. Từ lệnh: nút Truy vết"),
            ("Tổng quan", "Chỉ xem KPI, lọc ngày — không nhập chứng từ"),
        ],
        "Lưới chung: bấm dòng mở chi tiết. Không thấy nút = thiếu quyền Tạo/Sửa.",
    )

    story.append(Spacer(1, 0.5 * cm))
    story.append(P("— Hết tài liệu —", st["Small"]))

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Quy trình sản xuất Portal JustPlay",
        author="Portal JustPlay",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"OK: {OUT}")


if __name__ == "__main__":
    build()
