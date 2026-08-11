"""Máy cho IE lấy từ Quản lý thiết bị sản xuất (không dùng danh mục SxMachine)."""

from __future__ import annotations

from types import SimpleNamespace


def production_machine_qs():
    from equipment.models import Device
    from equipment.scope import SCOPE_PRODUCTION, filter_devices_for_scope

    return filter_devices_for_scope(Device.objects.all(), SCOPE_PRODUCTION)


def production_machine_count() -> int:
    return production_machine_qs().count()


def ie_machine_options(*, extra_code: str = '', limit: int | None = 400) -> list:
    """Danh sách máy (code + name) cho select/datalist IE."""
    qs = production_machine_qs().order_by('name', 'device_code')
    if limit:
        qs = qs[:limit]
    opts: list = []
    seen: set[str] = set()
    for device in qs:
        code = (device.device_code or '').strip()
        if not code or code.casefold() in seen:
            continue
        seen.add(code.casefold())
        opts.append(SimpleNamespace(code=code, name=(device.name or code).strip()))
    extra = (extra_code or '').strip()
    if extra and extra.casefold() not in seen:
        opts.insert(0, SimpleNamespace(code=extra, name=f'{extra} (đang dùng)'))
    return opts
