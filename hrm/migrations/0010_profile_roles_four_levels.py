from django.db import migrations, models

ROLE_MAP = {
    'HOD': 'TEAM_LEADER',
    'GM': 'DIRECTOR',
}


def migrate_roles(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    for profile in Profile.objects.all():
        new_role = ROLE_MAP.get(profile.role)
        if new_role:
            profile.role = new_role
            profile.save(update_fields=['role'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0009_division_model'),
    ]

    operations = [
        migrations.RunPython(migrate_roles, noop),
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[
                    ('EMPLOYEE', 'Nhân viên'),
                    ('TEAM_LEADER', 'Tổ trưởng'),
                    ('DIVISION_HEAD', 'Trưởng bộ phận'),
                    ('DIRECTOR', 'Giám đốc'),
                ],
                default='EMPLOYEE',
                max_length=20,
                verbose_name='Vai trò hệ thống',
            ),
        ),
        migrations.AlterField(
            model_name='profile',
            name='subordinates',
            field=models.ManyToManyField(
                blank=True,
                related_name='my_hod_managers',
                to='auth.user',
                verbose_name='Nhân viên dưới quyền',
            ),
        ),
    ]
