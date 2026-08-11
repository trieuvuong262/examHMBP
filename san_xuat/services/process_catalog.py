"""Danh mục công đoạn chuẩn dùng chung từ module IE + mẫu progress."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from san_xuat.ie_models import SxOperation, SxOperationGroup
from san_xuat.models import SxProcessName
from san_xuat.services.progress_template import GROUPS, canonical_process_label, progress_steps


def default_process_names() -> list[tuple[str, int]]:
    """Tên + thứ tự từ mẫu công đoạn chuẩn JustPlay."""
    return [(s.label, s.sequence) for s in progress_steps()]


# Giữ alias cũ cho migration / import tham chiếu
DEFAULT_PROCESS_NAMES: list[tuple[str, int]] = default_process_names()


def seed_default_process_names() -> int:
    created = 0
    for name, order in default_process_names():
        obj, was_created = SxProcessName.objects.get_or_create(
            name=name,
            defaults={"sort_order": order, "is_active": True},
        )
        if was_created:
            created += 1
        elif obj.sort_order != order or not obj.is_active:
            obj.sort_order = order
            obj.is_active = True
            obj.save(update_fields=["sort_order", "is_active"])
    return created


_STANDARD_STATUSES = [
    SxOperation.STATUS_APPROVED,
    SxOperation.STATUS_TRIAL,
    SxOperation.STATUS_DRAFT,
]


def _standard_operation_names() -> list[str]:
    """Tên công đoạn chuẩn: ưu tiên thứ tự mẫu, rồi bổ sung từ thư viện IE."""
    seen: set[str] = set()
    names: list[str] = []
    for step in progress_steps():
        label = (step.label or "").strip()
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        names.append(label)
    rows = (
        SxOperation.objects.filter(status__in=_STANDARD_STATUSES)
        .exclude(name_vi="")
        .values_list("name_vi", flat=True)
        .distinct()
        .order_by("name_vi")
    )
    for row in rows:
        label = (row or "").strip()
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        names.append(label)
    return names


def resolve_standard_process_name(name: str) -> str:
    """Chuẩn hoá về đúng tên công đoạn trong mẫu / thư viện IE."""
    raw = (name or "").strip()
    if not raw:
        return ""
    canon = canonical_process_label(raw)
    match = (
        SxOperation.objects.filter(status__in=_STANDARD_STATUSES, name_vi__iexact=canon)
        .exclude(name_vi="")
        .order_by("name_vi")
        .values_list("name_vi", flat=True)
        .first()
    )
    if match:
        return (match or "").strip()
    # fallback exact raw
    match = (
        SxOperation.objects.filter(status__in=_STANDARD_STATUSES, name_vi__iexact=raw)
        .exclude(name_vi="")
        .order_by("name_vi")
        .values_list("name_vi", flat=True)
        .first()
    )
    return (match or canon or raw).strip()


def process_catalog_choices(*, extra_value: str = "", blank_label: str = "— Chọn công đoạn —") -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", blank_label)]
    seen: set[str] = set()
    for name in _standard_operation_names():
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        choices.append((name, name))
    extra = (extra_value or "").strip()
    if extra and extra.casefold() not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def _hr_work_center_id(
    *,
    work_center=None,
    work_center_code: str = '',
    name_hint: str = '',
) -> int | None:
    """ID tổ trên form LSX (HRD-* nếu có, không thì CAT/MAY/…) — không để ID IE WC-*."""
    from san_xuat.services.capacity_from_hrm import mo_form_work_center_id

    return mo_form_work_center_id(
        work_center=work_center,
        work_center_code=work_center_code,
        name_hint=name_hint,
    )


def process_group_rows() -> list[dict]:
    """Nhóm công đoạn cho tab hồ sơ BOM (không liệt kê ~50 CĐ chi tiết)."""
    rows: list[dict] = []
    seen: set[str] = set()
    qs = (
        SxOperationGroup.objects.filter(is_active=True)
        .select_related("default_work_center")
        .order_by("sort_order", "code")
    )
    for grp in qs:
        name = (grp.name or grp.code or "").strip()
        code = (grp.code or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "code": code,
            "name": name,
            "text": f"{code} — {name}" if code and code.casefold() != key else name,
            "default_work_center_id": _hr_work_center_id(
                work_center=grp.default_work_center,
                work_center_code=grp.default_work_center_code or '',
                name_hint=f'{grp.process_stage_label} {name} {code}',
            ),
            "sort_order": grp.sort_order or 100,
        })
    if rows:
        return rows
    for i, grp in enumerate(GROUPS):
        name = (grp.label or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        rows.append({
            "code": grp.key,
            "name": name,
            "text": name,
            "default_work_center_id": _hr_work_center_id(
                work_center_code=grp.work_center_code,
                name_hint=name,
            ),
            "sort_order": (i + 1) * 10,
        })
    return rows


def process_group_choices(
    *,
    extra_value: str = "",
    blank_label: str = "— Chọn nhóm công đoạn —",
    rows: list[dict] | None = None,
) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("", blank_label)]
    seen: set[str] = set()
    for row in (rows if rows is not None else process_group_rows()):
        name = (row.get("name") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        choices.append((name, row.get("text") or name))
    extra = (extra_value or "").strip()
    if extra and extra.casefold() not in seen:
        choices.append((extra, f"{extra} (đang dùng)"))
    return choices


def process_group_meta(rows: list[dict] | None = None) -> dict[str, dict]:
    """Map tên/mã nhóm → metadata (bộ phận mặc định)."""
    meta: dict[str, dict] = {}
    for row in (rows if rows is not None else process_group_rows()):
        payload = {
            "code": row.get("code") or "",
            "name": row.get("name") or "",
            "default_work_center_id": row.get("default_work_center_id"),
        }
        name = (row.get("name") or "").strip()
        code = (row.get("code") or "").strip()
        if name:
            meta[name] = payload
            meta[name.casefold()] = payload
        if code:
            meta[code] = payload
            meta[code.upper()] = payload
    return meta


def resolve_process_group_name(name: str) -> str:
    """Chuẩn hoá về tên nhóm công đoạn; fallback thư viện CĐ (dữ liệu cũ)."""
    raw = (name or "").strip()
    if not raw:
        return ""
    folded = raw.casefold()
    upper = raw.upper()
    for row in process_group_rows():
        if folded == (row.get("name") or "").casefold():
            return (row.get("name") or "").strip()
        if upper == (row.get("code") or "").upper():
            return (row.get("name") or "").strip()
    return resolve_standard_process_name(raw)


@transaction.atomic
def apply_process_groups_to_bom(bom, group_codes: list[str], *, replace: bool = False) -> int:
    """Thêm ProcessStep theo nhóm đã chọn (bỏ qua nhóm đã có trên BOM)."""
    from san_xuat.models import ProcessStep

    selected = [(c or "").strip() for c in group_codes if (c or "").strip()]
    if not selected or bom is None:
        return 0
    selected_keys = {c.casefold() for c in selected}
    selected_keys.update(c.upper() for c in selected)

    if replace:
        bom.process_steps.all().delete()

    existing = list(bom.process_steps.all())
    existing_names = {(s.process_name or "").casefold() for s in existing}
    existing_codes = {(s.op_code or "").upper() for s in existing if s.op_code}
    max_seq = max((s.sequence or 0) for s in existing) if existing else 0

    created = 0
    for row in process_group_rows():
        name = (row.get("name") or "").strip()
        code = (row.get("code") or "").strip()
        if not name:
            continue
        if name.casefold() not in selected_keys and code.upper() not in selected_keys:
            continue
        if name.casefold() in existing_names or (code and code.upper() in existing_codes):
            continue
        max_seq += 10
        ensure_process_name(name)
        ProcessStep.objects.create(
            bom=bom,
            sequence=max_seq,
            process_name=name[:120],
            op_code=(code or "")[:30],
            norm_per_hour=Decimal("60"),
            work_center_id=row.get("default_work_center_id"),
            cost_per_hour=Decimal("0"),
            notes="",
        )
        created += 1
        existing_names.add(name.casefold())
        if code:
            existing_codes.add(code.upper())
    return created


def ensure_process_name(name: str) -> SxProcessName:
    """Đồng bộ mirror legacy SxProcessName cho các luồng cũ."""
    name = canonical_process_label(name) or (name or "").strip()
    if not name:
        raise ValueError("Tên công đoạn trống.")
    if len(name) > 120:
        raise ValueError("Tên công đoạn tối đa 120 ký tự.")
    existing = SxProcessName.objects.filter(name__iexact=name).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=["is_active"])
        if existing.name != name:
            existing.name = name
            existing.save(update_fields=["name"])
        return existing
    max_order = SxProcessName.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return SxProcessName.objects.create(
        name=name,
        sort_order=(max_order or 400) + 10,
        is_active=True,
    )
