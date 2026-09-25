"""Menu Quản lý KSK: chỉ HCNS - NV và HCNS - TP được xem, sửa giờ và xuất Excel."""

from django.db import migrations

HCNS_SLUGS = {'hcns-nhan-vien', 'hcns-truong-phong'}
MENU_KEY = 'ksk_manage'


def grant_ksk_manage(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    allowed = {
        'view': True,
        'create': False,
        'update': True,
        'delete': False,
        'export': True,
        'print': False,
    }
    denied = {action: False for action in allowed}
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        surveys = dict(perms.get('surveys') or {})
        menus = surveys.get('menus')
        if not isinstance(menus, dict) or not menus:
            continue
        menus = dict(menus)
        menus[MENU_KEY] = dict(allowed if (group.slug or '') in HCNS_SLUGS else denied)
        surveys['menus'] = menus
        if (group.slug or '') in HCNS_SLUGS:
            surveys['view'] = True
        perms['surveys'] = surveys
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def revoke_ksk_manage(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        surveys = dict(perms.get('surveys') or {})
        menus = surveys.get('menus')
        if not isinstance(menus, dict) or MENU_KEY not in menus:
            continue
        menus = dict(menus)
        menus.pop(MENU_KEY, None)
        surveys['menus'] = menus
        perms['surveys'] = surveys
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0112_seed_docs_cost_stats_menu'),
    ]

    operations = [
        migrations.RunPython(grant_ksk_manage, revoke_ksk_manage),
    ]
