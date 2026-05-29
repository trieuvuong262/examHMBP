import django.db.models.deletion
from django.db import migrations, models

DEFAULT_DEPARTMENTS = [
    'CÔNG TY TNHH JUST PLAY',
    'ĐẢM BẢO CHẤT LƯỢNG',
    'HÀNH CHÍNH NHÂN SỰ',
    'KẾ HOẠCH SẢN XUẤT',
    'KINH DOANH - MARKETING',
    'R&D',
    'SẢN XUẤT',
    'TÀI CHÍNH KẾ TOÁN',
]


def seed_and_migrate_departments(apps, schema_editor):
    Department = apps.get_model('hrm', 'Department')
    Profile = apps.get_model('hrm', 'Profile')

    cache = {}
    for index, name in enumerate(DEFAULT_DEPARTMENTS):
        dept, _ = Department.objects.get_or_create(
            name=name,
            defaults={'sort_order': index, 'is_active': True},
        )
        cache[name.lower()] = dept

    for profile in Profile.objects.all():
        old_name = (getattr(profile, 'department_old', '') or '').strip()
        if not old_name:
            continue
        key = old_name.lower()
        if key not in cache:
            dept, _ = Department.objects.get_or_create(
                name=old_name,
                defaults={'sort_order': 100, 'is_active': True},
            )
            cache[key] = dept
        profile.department_id = cache[key].id
        profile.save(update_fields=['department_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0007_profile_employee_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Tên phòng ban')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang sử dụng')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')),
            ],
            options={
                'verbose_name': 'Phòng ban',
                'verbose_name_plural': 'Phòng ban',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RenameField(
            model_name='profile',
            old_name='department',
            new_name='department_old',
        ),
        migrations.AddField(
            model_name='profile',
            name='department',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='profiles',
                to='hrm.department',
                verbose_name='Phòng ban',
            ),
        ),
        migrations.RunPython(seed_and_migrate_departments, noop),
        migrations.RemoveField(
            model_name='profile',
            name='department_old',
        ),
    ]
