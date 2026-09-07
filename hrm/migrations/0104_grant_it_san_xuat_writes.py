"""Nhóm IT đã xem menu Sản xuất/Kho nhưng thiếu Thêm/Sửa — không lưu được đơn, LSX, …"""

from django.db import migrations

SX_STACK = ('san_xuat', 'kho_npl', 'kho_san_pham')


def _is_it_group(name: str, slug: str) -> bool:
    n = (name or '').strip().casefold()
    s = (slug or '').strip().casefold()
    return n == 'it' or s == 'it' or s.startswith('it-') or n.startswith('it ')


def grant_forward(apps, schema_editor):
    from hrm.group_permissions import grant_supported_writes_on_viewed_menus

    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        if not _is_it_group(group.name or '', getattr(group, 'slug', '') or ''):
            continue
        perms = dict(group.module_permissions or {})
        changed = False
        for module_key in SX_STACK:
            raw = perms.get(module_key)
            if not isinstance(raw, dict):
                continue
            updated = grant_supported_writes_on_viewed_menus(raw, module_key=module_key)
            if updated != raw:
                perms[module_key] = updated
                changed = True
        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0103_fix_kpi_group_permissions'),
    ]

    operations = [
        migrations.RunPython(grant_forward, noop_reverse),
    ]
