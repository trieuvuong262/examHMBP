from django.db import migrations

SAMPLE_GROUP_CODES = (
    'tgd', 'dbcl', 'hcns', 'khsx', 'kd-mkt', 'rd', 'sx', 'tckt', 'it',
)
SAMPLE_DESC = 'Mẫu tham khảo — tuỳ chỉnh quyền và gán thủ công cho nhân viên.'


def mark_sample_groups(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for code in SAMPLE_GROUP_CODES:
        for level in ('nhan-vien', 'truong-phong'):
            PermissionGroup.objects.filter(slug=f'{code}-{level}').update(
                description=SAMPLE_DESC,
                is_system=False,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0025_department_groups_deletable'),
    ]

    operations = [
        migrations.RunPython(mark_sample_groups, noop),
    ]
