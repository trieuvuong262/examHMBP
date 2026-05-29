from django.db import migrations, models
import django.db.models.deletion


def seed_all_modules_for_departments(apps, schema_editor):
    Department = apps.get_model('hrm', 'Department')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    all_modules = [
        'announcements',
        'recruitment',
        'training',
        'assessment',
        'hrm',
        'kpi',
        'reports',
        'guide',
    ]
    for dept in Department.objects.all():
        DepartmentMenuPermission.objects.get_or_create(
            department_id=dept.id,
            defaults={'modules': all_modules},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0014_revert_division_department'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentMenuPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modules', models.JSONField(blank=True, default=list, help_text='Danh sách mã module. Để trống = cho phép tất cả.', verbose_name='Module được phép')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('department', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='menu_permissions', to='hrm.department', verbose_name='Phòng ban')),
            ],
            options={
                'verbose_name': 'Phân quyền menu phòng ban',
                'verbose_name_plural': 'Phân quyền menu phòng ban',
            },
        ),
        migrations.RunPython(seed_all_modules_for_departments, noop),
    ]
