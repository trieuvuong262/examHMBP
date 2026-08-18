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


def ie_machine_search(*, q: str = '', limit: int = 60) -> list[dict]:
    """Tìm máy sản xuất cho TomSelect (mở dropdown / gõ tìm)."""
    from django.db.models import Q

    qs = production_machine_qs().order_by('name', 'device_code')
    term = (q or '').strip()
    if term:
        qs = qs.filter(
            Q(device_code__icontains=term)
            | Q(name__icontains=term)
        )
    results: list[dict] = []
    seen: set[str] = set()
    for device in qs[: max(limit * 2, 120)]:
        code = (device.device_code or '').strip()
        if not code or code.casefold() in seen:
            continue
        seen.add(code.casefold())
        name = (device.name or code).strip()
        results.append({
            'id': code,
            'text': f'{code} — {name}',
            'code': code,
            'name': name,
        })
        if len(results) >= limit:
            break
    return results


def machine_options_for_codes(codes: list[str] | str) -> list[dict]:
    """Option TomSelect cho mã máy đã lưu (kể cả legacy không còn trong danh mục)."""
    if isinstance(codes, str):
        raw = (codes or '').replace(';', ',')
        tokens = [part.strip() for part in raw.split(',') if part.strip()]
    else:
        tokens = [str(part or '').strip() for part in (codes or []) if str(part or '').strip()]
    if not tokens:
        return []
    by_code: dict[str, object] = {}
    for device in production_machine_qs().only('device_code', 'name'):
        code = (device.device_code or '').strip()
        if code:
            by_code[code.casefold()] = device
    out: list[dict] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        device = by_code.get(key)
        if device:
            name = (device.name or device.device_code).strip()
            out.append({
                'code': device.device_code,
                'text': f'{device.device_code} — {name}',
            })
        else:
            out.append({'code': token, 'text': f'{token} (đang dùng)'})
    return out


def format_machine_codes_display(raw: str) -> str:
    """Hiển thị danh sách máy đã lưu — ưu tiên tên từ Quản lý thiết bị."""
    opts = machine_options_for_codes(raw)
    if not opts:
        return (raw or '').strip()
    return ', '.join(item['text'].replace(' (đang dùng)', '') for item in opts)
