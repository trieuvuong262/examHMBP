"""Dòng BOM theo Nhóm gom NPL — bung thành NPL thành viên.

Quy ước (đã chốt 2026-10-30):
- 1 dòng BOM = 1 NPL lẻ **hoặc** 1 nhóm gom (``BomLine.material_group``).
- Dòng nhóm bung thành mọi NPL thành viên **đang dùng**; mỗi thành viên nhận đủ
  định mức / hao hụt / size của dòng nhóm.
- Đơn hàng chụp kết quả bung vào ``bom_line_overrides`` lúc tạo đơn (snapshot);
  KH NPL / LSX / phiếu xuất tiếp tục làm việc theo mã NPL.
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


def expand_bom_lines(lines) -> list[ExpandedBomLine]:
    """Bung danh sách ``BomLine`` (giữ thứ tự) — dòng nhóm → các NPL thành viên."""
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
        for mat in members.get(ln.material_group_id, []):
            out.append(ExpandedBomLine(
                line=ln, material=mat, group_id=ln.material_group_id, group_name=name,
            ))
    return out


def duplicate_material_codes(bom) -> list[str]:
    """Mã NPL xuất hiện > 1 lần (cùng size) sau khi bung nhóm — để cảnh báo cộng dồn."""
    seen: dict[tuple, int] = {}
    lines = bom.lines.select_related('material', 'material_group').all()
    for item in expand_bom_lines(lines):
        key = ((item.material.code or '').strip(), (item.line.size_code or '').strip())
        seen[key] = seen.get(key, 0) + 1
    return sorted({code for (code, _size), n in seen.items() if n > 1 and code})


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
