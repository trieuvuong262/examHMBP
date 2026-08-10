"""Danh mục công đoạn chuẩn dùng chung từ module IE + mẫu progress."""

from __future__ import annotations

from san_xuat.ie_models import SxOperation
from san_xuat.models import SxProcessName
from san_xuat.services.progress_template import canonical_process_label, progress_steps


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
