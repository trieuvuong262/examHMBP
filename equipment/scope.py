"""Phạm vi menu Quản lý thiết bị — IT vs sản xuất."""

from __future__ import annotations

from django.urls import reverse

SCOPE_IT = 'it'
SCOPE_PRODUCTION = 'production'

SCOPE_LABELS = {
    SCOPE_IT: 'Quản lý thiết bị IT',
    SCOPE_PRODUCTION: 'Quản lý thiết bị sản xuất',
}

SCOPE_SHORT_LABELS = {
    SCOPE_IT: 'Thiết bị IT',
    SCOPE_PRODUCTION: 'Thiết bị sản xuất',
}


def scope_for_device(device) -> str:
    from equipment.services.device_categories import import_profile_for_code

    if device is None:
        return SCOPE_IT
    if import_profile_for_code(getattr(device, 'category', '')) == 'it':
        return SCOPE_IT
    return SCOPE_PRODUCTION


def filter_devices_for_scope(qs, scope: str | None):
    from equipment.services.device_categories import category_codes_for_profile

    if scope == SCOPE_IT:
        codes = category_codes_for_profile('it')
        return qs.filter(category__in=codes) if codes else qs.none()
    if scope == SCOPE_PRODUCTION:
        codes = category_codes_for_profile('machine')
        return qs.filter(category__in=codes) if codes else qs.none()
    return qs


def scope_from_path(path: str) -> str | None:
    normalized = (path or '').lower()
    if '/thiet-bi/san-xuat' in normalized:
        return SCOPE_PRODUCTION
    if '/thiet-bi/it' in normalized:
        return SCOPE_IT
    return None


def scope_url_name(base: str, scope: str | None) -> str:
    if scope == SCOPE_PRODUCTION:
        return f'{base}_production'
    if scope == SCOPE_IT:
        return f'{base}_it'
    return base


def scope_urls(scope: str | None) -> dict[str, str]:
    names = {
        'dashboard': scope_url_name('dashboard', scope),
        'device_list': scope_url_name('device_list', scope),
        'device_add': scope_url_name('device_add', scope),
        'import_export_hub': scope_url_name('import_export_hub', scope),
        'category_list': scope_url_name('category_list', scope),
        'export_devices': scope_url_name('export_devices', scope),
        'download_sample': scope_url_name('download_sample', scope),
        'import_devices': scope_url_name('import_devices', scope),
        'it_repair_list': scope_url_name('it_repair_list', scope),
    }
    urls = {key: reverse(f'equipment:{name}') for key, name in names.items()}
    urls['home'] = urls['dashboard']
    return urls


def scope_context(scope: str | None) -> dict:
    return {
        'equipment_scope': scope,
        'equipment_scope_label': SCOPE_LABELS.get(scope or '', ''),
        'equipment_scope_short': SCOPE_SHORT_LABELS.get(scope or '', ''),
        'equipment_urls': scope_urls(scope),
    }


def it_repair_detail_url(equipment_scope: str | None, pk) -> str:
    name = scope_url_name('it_repair_detail', equipment_scope)
    return reverse(f'equipment:{name}', args=[pk])


def merge_scope_context(request, equipment_scope: str | None = None, device=None) -> dict:
    scope = equipment_scope or scope_from_path(getattr(request, 'path', ''))
    if not scope and device is not None:
        scope = scope_for_device(device)
    if not scope:
        scope = SCOPE_IT
    return scope_context(scope)
