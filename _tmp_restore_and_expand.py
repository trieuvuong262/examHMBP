"""Restore san_xuat templates from Cursor local history, then expand abbreviations safely."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

HIST = Path(r"C:\Users\Vuong-IT\AppData\Roaming\Cursor\User\History")
DEST_ROOT = Path(r"d:\Project\PortalJustPlay\san_xuat\templates\san_xuat")

REPLS: list[tuple[str, str]] = [
    ("YCNTP — chứng từ nội bộ + liên kết phiếu nhập KiotViet", "Chứng từ nội bộ + liên kết phiếu nhập KiotViet"),
    ("Tạo YCNTP", "Tạo yêu cầu nhập thành phẩm"),
    ("Gửi YCNTP", "Gửi yêu cầu nhập thành phẩm"),
    ("Chưa có YCNTP.", "Chưa có yêu cầu nhập thành phẩm."),
    ("YCNTP {{", "Yêu cầu nhập thành phẩm {{"),
    ("YCNTP ", "Yêu cầu nhập thành phẩm "),
    ("YCNTP.", "yêu cầu nhập thành phẩm."),
    ("(YCNTP)", "(yêu cầu nhập thành phẩm)"),
    ("Tạo YCX", "Tạo yêu cầu xuất"),
    ("Duyệt YCX", "Duyệt yêu cầu xuất"),
    ("YCX liên quan", "Yêu cầu xuất liên quan"),
    ("Chưa có YCX", "Chưa có yêu cầu xuất"),
    ("YCX từ", "yêu cầu xuất từ"),
    ("YCX ", "Yêu cầu xuất "),
    (" YCX", " yêu cầu xuất"),
    ("(YCX)", "(yêu cầu xuất)"),
    ("Tạo YCM", "Tạo yêu cầu mua nguyên phụ liệu"),
    ("YCM ", "Yêu cầu mua nguyên phụ liệu "),
    ("(YCM)", "(yêu cầu mua nguyên phụ liệu)"),
    ("Tạo YCKT", "Tạo yêu cầu kiểm tra"),
    ("YCKT ", "Yêu cầu kiểm tra "),
    ("YCKT:", "Yêu cầu kiểm tra:"),
    ("(YCKT)", "(yêu cầu kiểm tra)"),
    ("Tạo TKSX", "Tạo thống kê sản xuất"),
    ("Ghi TKSX", "Ghi thống kê sản xuất"),
    ("TKSX liên quan", "Thống kê sản xuất liên quan"),
    ("TKSX nguồn", "Thống kê sản xuất nguồn"),
    ("TKSX:", "Thống kê sản xuất:"),
    ("TKSX ", "Thống kê sản xuất "),
    (" TKSX", " thống kê sản xuất"),
    ("(TKSX)", "(thống kê sản xuất)"),
    ("Tạo LSX", "Tạo lệnh sản xuất"),
    ("Cập nhật LSX", "Cập nhật lệnh sản xuất"),
    ("Danh sách LSX", "Danh sách lệnh sản xuất"),
    ("LSX nguồn", "Lệnh sản xuất nguồn"),
    ("LSX:", "Lệnh sản xuất:"),
    ("LSX ", "Lệnh sản xuất "),
    (" LSX", " lệnh sản xuất"),
    ("(LSX)", "(lệnh sản xuất)"),
    ("<th>LSX</th>", "<th>Lệnh sản xuất</th>"),
    ("<th>TKSX</th>", "<th>Thống kê sản xuất</th>"),
    ("Kế hoạch NPL", "Kế hoạch nguyên phụ liệu"),
    ("KHNVL", "kế hoạch nguyên phụ liệu"),
    ("KHTT", "kế hoạch tổng thể"),
    ("KHCT", "kế hoạch chi tiết"),
    ("Tạo DMH", "Tạo đơn mua hàng"),
    ("DMH ", "Đơn mua hàng "),
    ("(DMH)", "(đơn mua hàng)"),
    ("Bàn giao BTP", "Bàn giao bán thành phẩm"),
    ("Trả lại BTP", "Trả lại bán thành phẩm"),
    ("Trả BTP", "Trả bán thành phẩm"),
    ("trả BTP", "trả bán thành phẩm"),
    ("BTP ", "Bán thành phẩm "),
    (" BTP", " bán thành phẩm"),
    ("(BTP)", "(bán thành phẩm)"),
    ("NPL thừa", "Nguyên phụ liệu thừa"),
    ("Kho NPL", "Kho nguyên phụ liệu"),
    ("Phiếu xuất NPL", "Phiếu xuất nguyên phụ liệu"),
    ("Mã NPL", "Mã nguyên phụ liệu"),
    ("NPL ", "Nguyên phụ liệu "),
    (" NPL", " nguyên phụ liệu"),
    ("(NPL)", "(nguyên phụ liệu)"),
    ("NVL/BTP", "nguyên vật liệu / bán thành phẩm"),
    ("Mã NVL", "Mã nguyên vật liệu"),
    ("NVL ", "Nguyên vật liệu "),
    (" NVL", " nguyên vật liệu"),
    ("(NVL)", "(nguyên vật liệu)"),
    ("Tạo PKT", "Tạo phiếu kiểm tra"),
    ("PKT ", "Phiếu kiểm tra "),
    ("(PKT)", "(phiếu kiểm tra)"),
    ("Cảnh báo QC", "Cảnh báo chất lượng"),
    ("Tiêu chí QC", "Tiêu chí chất lượng"),
    ("Nhóm tiêu chí QC", "Nhóm tiêu chí chất lượng"),
    ("Bộ tiêu chuẩn QC", "Bộ tiêu chuẩn chất lượng"),
    ("Nhóm lỗi QC", "Nhóm lỗi chất lượng"),
    ("Lỗi QC", "Lỗi chất lượng"),
    ("Kết quả QC", "Kết quả kiểm tra chất lượng"),
    (" QC", " kiểm tra chất lượng"),
    ("(QC)", "(kiểm tra chất lượng)"),
    ("SL nhập TP", "Số lượng nhập thành phẩm"),
    ("nhập TP", "nhập thành phẩm"),
    ("Nhập TP", "Nhập thành phẩm"),
    ("Mã SP", "Mã sản phẩm"),
    ("Ngày YC", "Ngày yêu cầu"),
    ("Phiếu nhập KV", "Phiếu nhập KiotViet"),
    ("phiếu nhập KV", "phiếu nhập KiotViet"),
    ("Liên kết phiếu nhập KV", "Liên kết phiếu nhập KiotViet"),
    ("Đã liên kết phiếu nhập KV.", "Đã liên kết phiếu nhập KiotViet."),
    ("Mã đơn KV", "Mã đơn KiotViet"),
    ("đơn KV", "đơn KiotViet"),
    ("LTD nguồn", "Lệnh tháo dỡ nguồn"),
    ("Tạo LTD", "Tạo lệnh tháo dỡ"),
    ("LTD ", "Lệnh tháo dỡ "),
    ("(LTD)", "(lệnh tháo dỡ)"),
    ("Giá thành KH theo đơn", "Giá thành kế hoạch theo đơn"),
    ("Tạo GTKH", "Tạo giá thành kế hoạch"),
    ("GTKH ", "Giá thành kế hoạch "),
    ("Tạo bảng GT", "Tạo bảng giá thành"),
    ("GT thực", "Giá thành thực tế"),
    ("Hồ sơ SX", "Hồ sơ sản xuất"),
    ("Giao việc SX", "Giao việc sản xuất"),
    ("Năng lực SX", "Năng lực sản xuất"),
    ("vòng SX", "vòng sản xuất"),
    ("trạng thái SX", "trạng thái sản xuất"),
    ("Từ CĐ", "Từ công đoạn"),
    ("Về CĐ", "Về công đoạn"),
]


def protect(text: str) -> tuple[str, list[str]]:
    chunks: list[str] = []

    def stash(m: re.Match) -> str:
        chunks.append(m.group(0))
        return f"@@TAG{len(chunks)-1}@@"

    # Only Django tags — never nest attribute protection
    protected = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", stash, text, flags=re.DOTALL)
    return protected, chunks


def restore(text: str, chunks: list[str]) -> str:
    def unstash(m: re.Match) -> str:
        return chunks[int(m.group(1))]

    return re.sub(r"@@TAG(\d+)@@", unstash, text)


def expand_abbr(raw: str) -> str:
    body, chunks = protect(raw)
    for a, b in REPLS:
        body = body.replace(a, b)
    return restore(body, chunks)


def history_map() -> dict[str, Path]:
    """Map relative template path -> best clean history file."""
    out: dict[str, Path] = {}
    for entries_path in HIST.glob("*/entries.json"):
        try:
            data = json.loads(entries_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        res = unquote(data.get("resource", ""))
        marker = "/san_xuat/templates/san_xuat/"
        if marker not in res.replace("\\", "/"):
            continue
        rel = res.replace("\\", "/").split(marker, 1)[1]
        folder = entries_path.parent
        # pick latest entry that is clean
        ents = data.get("entries") or []
        chosen = None
        for ent in reversed(ents):
            fp = folder / ent["id"]
            if not fp.exists():
                continue
            raw = fp.read_bytes()
            if b"\x00TAG" in raw:
                continue
            chosen = fp
            break
        if chosen:
            out[rel] = chosen
    return out


def main() -> None:
    mapping = history_map()
    print(f"History clean files: {len(mapping)}")
    restored = 0
    for rel, src in sorted(mapping.items()):
        dest = DEST_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        text2 = expand_abbr(text)
        dest.write_text(text2, encoding="utf-8")
        restored += 1
        print("restored", rel)
    print("Restored+expanded:", restored)

    # Fix any remaining corrupted files not covered
    still = []
    for p in DEST_ROOT.rglob("*.html"):
        if b"\x00TAG" in p.read_bytes():
            still.append(p)
    print("Still corrupted:", len(still))
    for p in still:
        print(" ", p.relative_to(DEST_ROOT))


if __name__ == "__main__":
    main()
