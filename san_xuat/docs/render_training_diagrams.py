"""Sinh ảnh diagram tách riêng — khớp menu / nút thật trên Portal."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "diagrams"
FONT = r"C:\Windows\Fonts\arial.ttf"
FONT_B = r"C:\Windows\Fonts\arialbd.ttf"

RED = (185, 28, 28)
RED_DK = (127, 29, 29)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
LINE = (252, 165, 165)
WHITE = (255, 255, 255)
BG = (255, 255, 255)
BOX = (254, 242, 242)
BOX2 = (255, 247, 237)
BOX3 = (240, 253, 250)
BOX4 = (239, 246, 255)
STROKE = (220, 38, 38)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def _text_size(draw: ImageDraw.ImageDraw, text: str, fnt) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def rounded(draw: ImageDraw.ImageDraw, xy, fill, outline, width=2, radius=12):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def arrow_down(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int):
    draw.line((x, y0, x, y1 - 8), fill=STROKE, width=3)
    draw.polygon([(x, y1), (x - 7, y1 - 12), (x + 7, y1 - 12)], fill=STROKE)


def arrow_right(draw: ImageDraw.ImageDraw, x0: int, x1: int, y: int):
    draw.line((x0, y, x1 - 8, y), fill=STROKE, width=3)
    draw.polygon([(x1, y), (x1 - 12, y - 7), (x1 - 12, y + 7)], fill=STROKE)


def center_text(draw, cx, cy, lines, fnt, fill=INK, gap=4):
    heights = [_text_size(draw, ln, fnt)[1] for ln in lines]
    total = sum(heights) + gap * (len(lines) - 1)
    y = cy - total // 2
    for ln, h in zip(lines, heights):
        w, _ = _text_size(draw, ln, fnt)
        draw.text((cx - w // 2, y), ln, font=fnt, fill=fill)
        y += h + gap


def caption(draw, x, y, w, text, fnt):
    draw.text((x, y), text, font=fnt, fill=MUTED)


def render_portal_flow() -> Path:
    """Luồng Portal đúng menu sidebar hiện tại."""
    W, H = 1400, 1680
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    title_f = font(28, True)
    sub_f = font(15)
    box_t = font(17, True)
    box_b = font(14)
    small = font(13)

    d.text((60, 36), "LUỒNG SẢN XUẤT TRÊN PORTAL", font=title_f, fill=RED)
    d.text(
        (60, 78),
        "Khớp menu Sản xuất đang mở cho nhân viên  ·  không gồm màn đã ẩn (đóng gói, shop floor, giá thành, KHTT/KHCT)",
        font=sub_f,
        fill=MUTED,
    )
    d.line((60, 108, W - 60, 108), fill=LINE, width=2)

    steps = [
        (
            BOX4,
            (14, 165, 230),
            "1. Hồ sơ",
            ["Hồ sơ thiết kế sản phẩm — tab BOM + quy trình", "Duyệt công đoạn (IE) nếu mã mới"],
            "Menu: Sản xuất → Hồ sơ",
        ),
        (
            BOX,
            (14, 165, 230),
            "2. Đơn đặt hàng",
            ["Lên đơn đặt hàng  →  Xác nhận đơn đặt hàng", "Đơn vào tab Hàng đợi của Kế hoạch sản xuất"],
            "Menu: Sản xuất → Đơn đặt hàng",
        ),
        (
            BOX,
            (14, 165, 230),
            "3. Kế hoạch sản xuất",
            [
                "Tab Hàng đợi: xếp ưu tiên / tạm giữ / bấm Chuyển SX",
                "Modal Chuyển SX — chọn BOM & công đoạn  →  sinh lệnh",
                "Tab Lộ trình: kéo lịch theo tổ   ·   Tab Đã chuyển SX: theo dõi",
            ],
            "Menu: Sản xuất → Kế hoạch SX → Kế hoạch sản xuất",
        ),
        (
            BOX2,
            (14, 165, 255),
            "4. Phân công SX  (xưởng)",
            [
                "Tiến độ hàng hoá — nhìn mọi tổ / mọi lệnh",
                "Từng tổ: Nhận sản xuất  →  Phân công  →  ghi tiến độ  →  Hoàn thành",
                "Thứ tự tổ: Cắt → In ép → Thêu → May → Ủi gấp xếp → Giao hàng",
            ],
            "Menu: Sản xuất → Phân công SX",
        ),
        (
            BOX2,
            (14, 165, 230),
            "5. Điều phối  (song song / sau khi đã có lệnh)",
            [
                "Lệnh sản xuất  ·  Yêu cầu xuất vật tư  (duyệt → phiếu xuất Kho NPL)",
                "Tình hình bàn giao  ·  Yêu cầu nhập thành phẩm",
            ],
            "Menu: Sản xuất → Điều phối",
        ),
        (
            BOX,
            (14, 165, 210),
            "6. Kiểm tra chất lượng",
            ["Tiến độ QC  ·  Phiếu kiểm tra (tab theo tổ)  ·  Cảnh báo  ·  Hàng không đạt"],
            "Menu: Sản xuất → Kiểm tra chất lượng",
        ),
        (
            BOX3,
            (14, 165, 190),
            "7. Kho sản phẩm  →  Báo cáo",
            ["Nhập thành phẩm vào kho  ·  Truy xuất nguồn gốc  ·  Báo cáo vận hành"],
            "Menu: Kho sản phẩm  ·  Báo cáo",
        ),
    ]

    y = 130
    cx = W // 2
    box_w = 1080
    x0 = (W - box_w) // 2
    for i, (fill, _pad, head, body, menu) in enumerate(steps):
        h = 86 + 22 * len(body)
        rounded(d, (x0, y, x0 + box_w, y + h), fill, STROKE, 2, 14)
        d.rectangle((x0, y, x0 + 10, y + h), fill=RED)
        d.text((x0 + 28, y + 14), head, font=box_t, fill=RED_DK)
        d.text((x0 + 28, y + 42), menu, font=small, fill=MUTED)
        ty = y + 66
        for line in body:
            d.text((x0 + 28, ty), "•  " + line, font=box_b, fill=INK)
            ty += 22
        if i < len(steps) - 1:
            arrow_down(d, cx, y + h, y + h + 28)
        y += h + 28

    # side note
    note_y = H - 78
    rounded(d, (60, note_y, W - 60, H - 28), (248, 250, 252), (203, 213, 225), 1, 10)
    d.text(
        (80, note_y + 14),
        "Nhánh phụ (khi thiếu vải / NPL):  Kế hoạch NPL  →  Yêu cầu mua NPL  →  Kho NPL (phiếu nhập).  "
        "Thuê gia công nằm trong Phân công SX — không thay tổ nội bộ khi phiếu GC đang mở.",
        font=small,
        fill=MUTED,
    )

    path = OUT / "01-luong-portal.png"
    img.save(path, "PNG")
    return path


def render_shopfloor() -> Path:
    """Sơ đồ riêng — 6 tổ trên Phân công SX + công đoạn catalog."""
    W, H = 1680, 1180
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    title_f = font(28, True)
    sub_f = font(15)
    team_t = font(16, True)
    team_b = font(13)
    small = font(13)

    d.text((56, 32), "CÁC BƯỚC SẢN XUẤT TRÊN XƯỞNG", font=title_f, fill=RED)
    d.text(
        (56, 74),
        "Menu Phân công SX  ·  mỗi tổ: Nhận sản xuất → Phân công → ghi tiến độ → Hoàn thành   "
        "·  tổ sau không bị chặn vì tổ trước chưa xong",
        font=sub_f,
        fill=MUTED,
    )
    d.line((56, 104, W - 56, 104), fill=LINE, width=2)

    teams = [
        ("1. Tổ cắt", "/cong-viec-to/cat/", ["Áo TT + TS + Tay", "Quần", "Phối quần"], BOX4),
        (
            "2. Tổ in ép",
            "/cong-viec-to/inep/",
            ["Lá cổ  ·  Trụ", "In giấy", "Thân trước / sau", "Tay"],
            BOX2,
        ),
        ("3. Tổ thêu", "/cong-viec-to/theu/", ["TT áo", "TT quần"], BOX),
        (
            "4. Tổ may",
            "/cong-viec-to/may/",
            ["May áo (cổ, trụ, vai, tay…)", "May quần (đáy, sườn, thun)", "Cắt chỉ · Kiểm · Giao may"],
            BOX,
        ),
        ("5. Tổ ủi gấp xếp", "/cong-viec-to/ht/", ["Kiểm hàng", "Ủi", "Gấp xếp"], (243, 232, 255)),
        ("6. Tổ giao hàng", "/cong-viec-to/gh/", ["Giao hàng thành phẩm"], BOX3),
    ]

    n = len(teams)
    gap = 18
    margin = 48
    box_w = (W - margin * 2 - gap * (n - 1)) // n
    box_h = 248
    y = 140
    for i, (title, url, items, fill) in enumerate(teams):
        x = margin + i * (box_w + gap)
        rounded(d, (x, y, x + box_w, y + box_h), fill, STROKE, 2, 14)
        d.text((x + 14, y + 14), title, font=team_t, fill=RED_DK)
        d.text((x + 14, y + 42), url, font=small, fill=MUTED)
        ty = y + 72
        for it in items:
            d.text((x + 14, ty), "•  " + it, font=team_b, fill=INK)
            ty += 28
        if i < n - 1:
            arrow_right(d, x + box_w, x + box_w + gap, y + box_h // 2)

    # action bar
    ay = y + box_h + 48
    rounded(d, (margin, ay, W - margin, ay + 88), BOX, STROKE, 2, 12)
    acts = ["Nhận sản xuất", "Phân công nhân viên", "Ghi tiến độ trên phiếu tổ", "Hoàn thành (khóa tổ)"]
    aw = (W - margin * 2 - 40) // 4
    for i, a in enumerate(acts):
        ax = margin + 20 + i * aw
        rounded(d, (ax + 8, ay + 18, ax + aw - 24, ay + 70), WHITE, STROKE, 2, 10)
        center_text(d, ax + (aw - 16) // 2, ay + 44, [a], font(15, True), RED_DK)
        if i < 3:
            arrow_right(d, ax + aw - 22, ax + aw + 6, ay + 44)

    # parallel
    py = ay + 120
    d.text((margin, py), "Song song trên Portal (không nằm trong board tổ)", font=font(16, True), fill=RED_DK)
    cards = [
        ("Điều phối", "Lệnh sản xuất\nYêu cầu xuất vật tư\nTình hình bàn giao\nYêu cầu nhập TP"),
        ("Kho NPL", "Duyệt xuất từ YCX\nPhiếu xuất ghi sổ\nNhập mua nếu thiếu"),
        ("QC", "Phiếu kiểm tra theo tổ\nCảnh báo chất lượng\nHàng không đạt (NCR)"),
        ("Kho sản phẩm", "Nhận thành phẩm\nTồn / phiếu nhập\nTruy xuất nguồn gốc"),
    ]
    cw = (W - margin * 2 - gap * 3) // 4
    ch = 168
    cy = py + 36
    for i, (h, body) in enumerate(cards):
        x = margin + i * (cw + gap)
        rounded(d, (x, cy, x + cw, cy + ch), WHITE, (203, 213, 225), 2, 12)
        d.text((x + 16, cy + 14), h, font=font(16, True), fill=INK)
        for j, ln in enumerate(body.split("\n")):
            d.text((x + 16, cy + 48 + j * 26), "•  " + ln, font=team_b, fill=INK)

    d.text(
        (margin, H - 42),
        "Nguồn catalog: san_xuat/services/progress_template.py  ·  nút trên board: team_work_board.html",
        font=small,
        fill=MUTED,
    )

    path = OUT / "02-buoc-xuong.png"
    img.save(path, "PNG")
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p1 = render_portal_flow()
    p2 = render_shopfloor()
    print(f"OK: {p1}")
    print(f"OK: {p2}")


if __name__ == "__main__":
    main()
