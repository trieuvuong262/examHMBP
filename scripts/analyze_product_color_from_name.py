"""Khảo sát khả năng bóc mã màu từ tên sản phẩm (chỉ đọc, không sửa dữ liệu).

Bối cảnh: kho_sp_product.color_code rỗng toàn bộ, nhưng phần lớn tên sản phẩm có
chứa tên màu (vd. "Áo lót body xanh da"). Script đo xem bóc được bao nhiêu, chỗ nào
nhập nhằng, chỗ nào không bóc được — làm căn cứ cho docs/integrations/central-product/.

Chạy:
    docker compose run --rm --no-deps -v /opt/portaljustplay:/app web \
        python scripts/analyze_product_color_from_name.py --out docs/integrations/central-product

Lưu ý: so khớp theo biên từ (\\b) để "Cam" không dính vào "CAMO", và ưu tiên tên màu
dài hơn để "Xanh đen" không bị hiểu thành "Đen".
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django  # noqa: E402

django.setup()

from kho_san_pham.models import Product  # noqa: E402
from kiotviet.models import KvProductAttribute  # noqa: E402
from san_xuat.hub_models import SxColor  # noqa: E402

NON_COLOR_ATTRS = {"SIZE", "FORM"}


def load_vocabulary() -> dict[str, str]:
    """Tên màu (đã casefold) -> tên gốc để hiển thị."""
    names: set[str] = set()

    names.update(
        KvProductAttribute.objects.exclude(attribute_name__in=NON_COLOR_ATTRS)
        .values_list("attribute_value", flat=True)
        .distinct()
    )
    names.update(SxColor.objects.values_list("name", flat=True))

    vocab: dict[str, str] = {}
    for raw in names:
        cleaned = re.sub(r"\s+", " ", (raw or "").strip())
        if len(cleaned) < 2:
            continue
        vocab.setdefault(cleaned.casefold(), cleaned)
    return vocab


def build_patterns(vocab: dict[str, str]) -> list[tuple[str, re.Pattern]]:
    """Sắp theo độ dài giảm dần để tên màu dài được xét trước."""
    ordered = sorted(vocab, key=len, reverse=True)
    return [(key, re.compile(rf"\b{re.escape(key)}\b")) for key in ordered]


def find_colors(text: str, patterns: list[tuple[str, re.Pattern]]) -> list[str]:
    """Trả về các tên màu tìm thấy, đã loại tên màu bị chứa trong tên dài hơn."""
    if not text:
        return []
    haystack = re.sub(r"\s+", " ", text).casefold()

    hits = [key for key, pattern in patterns if pattern.search(haystack)]
    if len(hits) <= 1:
        return hits

    # "Xanh đen" đã khớp thì bỏ "Đen"; "Trắng xanh đen" thì bỏ cả "Trắng xanh"
    return [h for h in hits if not any(h != other and h in other for other in hits)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/integrations/central-product")
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()

    vocab = load_vocabulary()
    patterns = build_patterns(vocab)

    qs = Product.objects.filter(color_code="").only("id", "code", "name", "full_name")

    total = 0
    ambiguous_count = 0
    unresolved_count = 0
    resolved: Counter[str] = Counter()
    resolved_from: Counter[str] = Counter()
    # Gom theo tên sản phẩm: một tên thường lặp cho hàng chục size, rà soát theo
    # tên thì người duyệt chỉ phải xem vài chục dòng thay vì vài trăm.
    ambiguous_by_name: Counter[tuple[str, str]] = Counter()
    unresolved_by_name: Counter[str] = Counter()
    per_color_examples: dict[str, list[str]] = defaultdict(list)

    for product in qs.iterator(chunk_size=500):
        total += 1

        matched_text = product.name or ""
        hits = find_colors(matched_text, patterns)
        source = "name"
        if not hits:
            matched_text = product.full_name or ""
            hits = find_colors(matched_text, patterns)
            source = "full_name"

        if not hits:
            unresolved_count += 1
            unresolved_by_name[product.name or "(không tên)"] += 1
            continue

        if len(hits) > 1:
            ambiguous_count += 1
            key = (matched_text, " + ".join(sorted(vocab[h] for h in hits)))
            ambiguous_by_name[key] += 1
            continue

        color = vocab[hits[0]]
        resolved[color] += 1
        resolved_from[source] += 1
        if len(per_color_examples[color]) < 1:
            per_color_examples[color].append(f"{matched_text}  _({source})_")

    resolved_total = sum(resolved.values())
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "color-extraction-report.md")

    lines = [
        "# Khảo sát bóc màu từ tên sản phẩm",
        "",
        "Sinh tự động bởi `scripts/analyze_product_color_from_name.py`. Chỉ đọc dữ liệu.",
        "",
        "## Kết quả tổng hợp",
        "",
        "| Nhóm | Số dòng | Tỷ lệ |",
        "|---|---|---|",
    ]

    def row(label: str, value: int) -> str:
        pct = f"{value / total * 100:.1f}%" if total else "—"
        return f"| {label} | {value:,} | {pct} |"

    lines.append(row("Bóc được đúng 1 màu", resolved_total))
    lines.append(row("Nhập nhằng (nhiều màu trong tên)", ambiguous_count))
    lines.append(row("Không bóc được", unresolved_count))
    lines.append(f"| **Tổng dòng chưa có màu** | **{total:,}** | 100% |")
    lines.extend(
        [
            "",
            f"Từ vựng đối chiếu: **{len(vocab)}** tên màu "
            f"(gộp từ thuộc tính KiotViet và bảng `san_xuat_sxcolor`).",
            "",
            f"Nguồn bóc được: `name` {resolved_from['name']:,} dòng, "
            f"`full_name` {resolved_from['full_name']:,} dòng.",
            "",
            "## Phân bổ theo màu",
            "",
            "Cột cuối là đoạn text đã khớp, kèm trường lấy được — dùng để phát hiện khớp sai.",
            "",
            "| Màu | Số dòng | Text đã khớp |",
            "|---|---|---|",
        ]
    )
    for color, count in resolved.most_common():
        example = per_color_examples[color][0] if per_color_examples[color] else ""
        lines.append(f"| {color} | {count:,} | {example} |")

    lines.extend(
        [
            "",
            "## Tổ hợp nhiều màu — cần cấp mã mới",
            "",
            f"{ambiguous_count:,} dòng SKU, gom lại còn **{len(ambiguous_by_name):,} tên sản phẩm**. "
            "Theo quyết định nghiệp vụ, mỗi tổ hợp được cấp một mã màu riêng.",
            "",
        ]
    )
    if ambiguous_by_name:
        lines.extend(["| Tên sản phẩm | Tổ hợp màu | Số SKU |", "|---|---|---|"])
        for (name, combo), count in ambiguous_by_name.most_common(args.samples):
            lines.append(f"| {name} | {combo} | {count} |")
        if len(ambiguous_by_name) > args.samples:
            lines.append("")
            lines.append(f"… và {len(ambiguous_by_name) - args.samples:,} tên nữa.")
    else:
        lines.append("Không có.")

    lines.extend(
        [
            "",
            "## Không bóc được",
            "",
            f"{unresolved_count:,} dòng SKU, gom lại còn **{len(unresolved_by_name):,} tên sản phẩm**.",
            "",
        ]
    )
    if unresolved_by_name:
        lines.extend(["| Tên sản phẩm | Số SKU |", "|---|---|"])
        for name, count in unresolved_by_name.most_common(args.samples):
            lines.append(f"| {name} | {count} |")
        if len(unresolved_by_name) > args.samples:
            lines.append("")
            lines.append(f"… và {len(unresolved_by_name) - args.samples:,} tên nữa.")
    else:
        lines.append("Không có.")

    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Tổng dòng chưa có màu: {total:,}")
    print(f"  bóc được 1 màu : {resolved_total:,}")
    print(f"  tổ hợp nhiều màu: {ambiguous_count:,} ({len(ambiguous_by_name):,} tên)")
    print(f"  không bóc được : {unresolved_count:,} ({len(unresolved_by_name):,} tên)")
    print(f"Báo cáo: {path}")


if __name__ == "__main__":
    main()
