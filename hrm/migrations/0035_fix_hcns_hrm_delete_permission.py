from django.db import migrations


def fix_hcns_employee_hrm_delete(apps, schema_editor):
    """NV HCNS: thêm/sửa NV được phép, không được xóa (khớp department_permission_templates)."""
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    from hrm.department_permission_templates import DEPARTMENT_PERMISSION_TEMPLATES

    hcns = next(t for t in DEPARTMENT_PERMISSION_TEMPLATES if t['code'] == 'hcns')
    group = PermissionGroup.objects.filter(slug='hcns-nhan-vien').first()
    if not group:
        return

    perms = dict(group.module_permissions or {})
    perms['hrm'] = dict(hcns['employee']['hrm'])
    perms['recruitment'] = dict(hcns['employee']['recruitment'])
    group.module_permissions = perms
    group.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0034_department_position'),
    ]

    operations = [
        migrations.RunPython(fix_hcns_employee_hrm_delete, noop),
    ]
