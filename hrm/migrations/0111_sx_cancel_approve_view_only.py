"""Duyệt hủy chỉ còn quyền Xem, và tắt mặc định để gán trong phân quyền."""

from django.db import migrations


def lock_cancel_perm(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus or 'sx_cancel_approve' not in menus:
            continue
        menus['sx_cancel_approve'] = {
            'view': False,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
            'print': False,
        }
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0110_seed_sx_cancel_approve_menu'),
    ]

    operations = [
        migrations.RunPython(lock_cancel_perm, noop),
    ]
