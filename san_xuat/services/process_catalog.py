"""Danh mục công đoạn SX — choices + thêm mới."""

from __future__ import annotations

from san_xuat.models import SxProcessName

# Seed từ công đoạn phổ biến trên báo cáo SX (đã chuẩn hoá).
DEFAULT_PROCESS_NAMES: list[tuple[str, int]] = [
    ("Ủi", 10),
    ("Kiểm", 20),
    ("Gấp xếp", 30),
    ("Cắt chỉ", 40),
    ("Kiểm lỗi", 50),
    ("Kiểm hàng", 60),
    ("Diễu đáy sau", 70),
    ("Diễu đáy trước", 80),
    ("Diễu dây", 90),
    ("Tra tay", 100),
    ("Tra bo cổ", 110),
    ("Tra bo tay", 120),
    ("Ép logo", 130),
    ("Ép nhãn size", 140),
    ("Ép lai", 150),
    ("Vắt sườn", 160),
    ("Vắt vai", 170),
    ("Ráp đáy", 180),
    ("Ráp sườn", 190),
    ("Ráp vai", 200),
    ("May dây cổ", 210),
    ("Nối bo cổ", 220),
    ("Nhiễu cổ trước", 230),
    ("Dán tem gấp xếp", 240),
    ("Bấm mạc", 250),
    ("Vô thun quần", 260),
    ("Dập lưng quần", 270),
    ("Lấy dấu đóng nút", 280),
    ("Chạy phi", 290),
    ("In chuyển nhiệt", 300),
    ("Cắt vải theo rập", 310),
    ("In / thêu logo", 320),
    ("May thân áo", 330),
    ("QC thành phẩm", 340),
    ("Ủi — đóng gói", 350),
    ("Đóng gói", 360),
]


def seed_default_process_names() -> int:
    created = 0
    for name, order in DEFAULT_PROCESS_NAMES:
        _, was_created = SxProcessName.objects.get_or_create(
            name=name,
            defaults={"sort_order": order, "is_active": True},
        )
        if was_created:
            created += 1
    return created


def process_catalog_choices(*, extra_value: str = "", blank_label: str = "— Chọn công đoạn —") -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", blank_label)]
    seen: set[str] = set()
    for row in SxProcessName.objects.filter(is_active=True).order_by("sort_order", "name"):
        name = (row.name or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        choices.append((name, name))
    extra = (extra_value or "").strip()
    if extra and extra.casefold() not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def ensure_process_name(name: str) -> SxProcessName:
    name = (name or "").strip()
    if not name:
        raise ValueError("Tên công đoạn trống.")
    if len(name) > 120:
        raise ValueError("Tên công đoạn tối đa 120 ký tự.")
    existing = SxProcessName.objects.filter(name__iexact=name).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=["is_active"])
        return existing
    max_order = SxProcessName.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return SxProcessName.objects.create(
        name=name,
        sort_order=(max_order or 400) + 10,
        is_active=True,
    )
