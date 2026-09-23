"""Đăng ký du lịch: Thêm cho mọi nhóm; Sửa, Xóa, Xuất Excel cho HCNS - NV và HCNS - TP."""

from django.db import migrations

HCNS_SLUGS = {'hcns-nhan-vien', 'hcns-truong-phong'}
HCNS_NAMES = {'hcns - nv', 'hcns - tp', 'hcns-nv', 'hcns-tp'}
TRIP_ACTIONS = ('view', 'create', 'update', 'delete', 'export', 'print')


def _is_hcns_manage(group) -> bool:
    slug = (group.slug or '').strip().lower()
    if slug in HCNS_SLUGS:
        return True
    name = ' '.join((group.name or '').strip().lower().replace('—', '-').replace('–', '-').split())
    return name in HCNS_NAMES


def _grant(perms, *, manage: bool) -> dict:
    perms = dict(perms or {})
    utilities = dict(perms.get('utilities') or {})
    menus = dict(utilities.get('menus') or {})
    trip = dict(menus.get('trip_schedule') or {})
    for action in TRIP_ACTIONS:
        trip.setdefault(action, False)
    trip['create'] = True
    if manage:
        trip['update'] = True
        trip['delete'] = True
        trip['export'] = True
    else:
        trip['update'] = False
        trip['delete'] = False
        trip['export'] = False
    menus['trip_schedule'] = trip
    utilities['menus'] = menus
    perms['utilities'] = utilities
    return perms


def grant_trip_permissions(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')

    for group in PermissionGroup.objects.all():
        group.module_permissions = _grant(
            group.module_permissions,
            manage=_is_hcns_manage(group),
        )
        group.save(update_fields=['module_permissions'])

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'utilities' not in modules:
            modules.append('utilities')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0108_add_kho_vat_tu_to_sx_stack'),
    ]

    operations = [
        migrations.RunPython(grant_trip_permissions, noop),
    ]
