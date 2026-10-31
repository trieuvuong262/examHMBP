"""Dòng BOM theo Nhóm gom NPL — bung thành NPL thành viên.

Quy ước (chốt lại 2026-10-31):
- 1 dòng BOM = 1 NPL lẻ HOẶC 1 nhóm gom (BomLine.material_group).
- Hồ sơ thiết kế là cho 1 sản phẩm: dòng nhóm = MỘT phần định mức (vd 1 nhãn size
  cho 1 SP), KHÔNG phải mỗi thành viên nhận đủ định mức. Costing / thống kê chi phí
  tính 1 lần với giá đại diện (bình quân giá các thành viên).
- Qua đơn hàng: dòng nhóm bung thành mọi NPL thành viên đang dùng, ĐM gốc của
  từng thành viên = ĐM dòng nhóm, nhưng NHU CẦU mặc định = 0 (qty_mode='qty',
  qty=0) để người lên đơn tự chia theo size / thực tế. Riêng thành viên có
  Material.size trùng 1 size trong đơn thì tự nhận ĐM đầy đủ cho đúng size đó.
- KH NPL / LSX / phiếu xuất tiếp tục làm việc theo mã NPL.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpandedBomLine:
    line: object  # san_xuat.models.BomLine
    material: object  # kho_npl.models.Material
    group_id: int | None = None
    group_name: str = ''


def group_members_map(group_ids) -> dict[int, list]:
    """``{group_id: [Material đang dùng, sắp theo mã]}`` — 1 query cho nhiều nhóm."""
    from kho_npl.models import Material

    ids = {int(g) for g in group_ids if g}
    out: dict[int, list] = {gid: [] for gid in ids}
    if not ids:
        return out
    qs = (
        Material.objects.filter(material_group_id__in=ids, is_active=True)
        .select_related('unit')
        .order_by('code', 'pk')
    )
    for mat in qs:
        out.setdefault(mat.material_group_id, []).append(mat)
    return out


def expand_bom_lines(lines, *, representative: bool = False) -> list[ExpandedBomLine]:
    """Bung danh sách ``BomLine`` (giữ thứ tự) — dòng nhóm → các NPL thành viên.

    ``representative=True``: dòng nhóm chỉ lấy 1 NPL đại diện (định mức cho 1 SP,
    không nhân theo số thành viên) — dùng cho tháo dỡ / thống kê theo thiết kế.
    """
    lines = list(lines)
    members = group_members_map(
        ln.material_group_id for ln in lines if ln.material_group_id and not ln.material_id
    )
    out: list[ExpandedBomLine] = []
    for ln in lines:
        if ln.material_id:
            out.append(ExpandedBomLine(line=ln, material=ln.material))
            continue
        if not ln.material_group_id:
            continue
        name = getattr(ln.material_group, 'name', '') or ''
        mats = members.get(ln.material_group_id, [])
        if representative:
            mats = mats[:1]
        for mat in mats:
            out.append(ExpandedBomLine(
                line=ln, material=mat, group_id=ln.material_group_id, group_name=name,
            ))
    return out


def group_unit_price(members) -> 'Decimal':
    """Giá đại diện của 1 dòng nhóm gom cho 1 SP = bình quân giá các thành viên.

    Dòng nhóm là 1 phần định mức (không phải mỗi thành viên nhận đủ ĐM),
    nên costing không cộng dồn giá mọi thành viên.
    """
    from decimal import Decimal

    from kho_npl.services.batches import material_avg_price

    members = list(members or [])
    if not members:
        return Decimal('0')
    total = sum((material_avg_price(m) for m in members), Decimal('0'))
    return (total / Decimal(len(members))).quantize(Decimal('0.01'))


def group_representative(members):
    """NPL đại diện của nhóm (thành viên đầu theo mã) — dùng cho danh mục / ĐVT."""
    members = list(members or [])
    return members[0] if members else None


def _size_key(raw) -> str:
    return str(raw or '').strip().casefold()


def member_matches_size(material, size_keys: set[str]) -> bool:
    """Thành viên nhóm có Material.size trùng 1 size trong đơn?"""
    raw = _size_key(getattr(material, 'size', ''))
    if not raw or not size_keys:
        return False
    if raw in size_keys:
        return True
    # Material.size có thể là "S, M" / "S/M"
    import re

    parts = {p for p in re.split(r'[\s,;/|]+', raw) if p}
    return bool(parts & size_keys)


def duplicate_material_codes(bom) -> list[str]:
    """Mã NPL xuất hiện > 1 lần (cùng size) sau khi bung nhóm — để cảnh báo cộng dồn."""
    seen: dict[tuple, int] = {}
    lines = bom.lines.select_related('material', 'material_group').all()
    for item in expand_bom_lines(lines):
        key = ((item.material.code or '').strip(), (item.line.size_code or '').strip())
        seen[key] = seen.get(key, 0) + 1
    return sorted({code for (code, _size), n in seen.items() if n > 1 and code})


def duplicate_material_details(bom) -> list[str]:
    """Mô tả từng NPL trùng: ``"CODE (TT 19, 21)"`` hoặc ``"CODE (TT 5, nhóm L9 – TT 30)"``."""
    seen: dict[tuple, list[str]] = {}
    lines = bom.lines.select_related('material', 'material_group').order_by('sort_order', 'id')
    for item in expand_bom_lines(lines):
        code = (item.material.code or '').strip()
        if not code:
            continue
        key = (code, (item.line.size_code or '').strip())
        where = f'TT {item.line.sort_order}'
        if item.group_id:
            where = f'nhóm {item.group_name or item.group_id} – {where}'
        seen.setdefault(key, []).append(where)
    return [
        f'{code} ({", ".join(places)})'
        for (code, _size), places in sorted(seen.items())
        if len(places) > 1
    ]


def empty_group_lines(lines) -> list:
    """Dòng nhóm không còn NPL thành viên đang dùng (để cảnh báo)."""
    lines = [ln for ln in lines if ln.material_group_id and not ln.material_id]
    members = group_members_map(ln.material_group_id for ln in lines)
    return [ln for ln in lines if not members.get(ln.material_group_id)]


def dissolve_group_bom_lines(group, *, user=None) -> int:
    """Trước khi xóa nhóm gom: đổi mọi dòng BOM trỏ nhóm thành dòng NPL lẻ.

    Mỗi thành viên đang dùng nhận nguyên ĐM/hao hụt/size/NVL thay thế của dòng nhóm.
    Ghi audit BOM. Trả về số dòng nhóm đã đổi.
    """
    from django.db import transaction

    from san_xuat.models import BomLine
    from san_xuat.services.bom_audit import bom_diff, bom_snapshot, log_bom_event

    group_lines = list(
        BomLine.objects.filter(material_group=group, material__isnull=True)
        .select_related('bom')
        .order_by('bom_id', 'sort_order', 'id')
    )
    if not group_lines:
        return 0
    members = group_members_map([group.pk]).get(group.pk, [])
    by_bom: dict[int, list] = {}
    for ln in group_lines:
        by_bom.setdefault(ln.bom_id, []).append(ln)
    with transaction.atomic():
        for lines in by_bom.values():
            bom = lines[0].bom
            before = bom_snapshot(bom)
            for ln in lines:
                for mat in members:
                    BomLine.objects.create(
                        bom=bom,
                        material=mat,
                        substitute_material=ln.substitute_material,
                        qty=ln.qty,
                        scrap_pct=ln.scrap_pct,
                        size_code=ln.size_code,
                        notes=(ln.notes or group.name or '')[:255],
                        sort_order=ln.sort_order,
                    )
                ln.delete()
            after = bom_snapshot(bom)
            changes = bom_diff(before, after)
            changes['snapshot'] = after
            log_bom_event(
                bom=bom,
                action='update',
                summary=f'Xóa nhóm gom {group.name} — tách thành {len(members)} NPL lẻ',
                changes=changes,
                user=user,
            )
    return len(group_lines)
