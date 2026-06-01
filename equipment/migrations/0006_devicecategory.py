# Generated manually for DeviceCategory CRUD

from django.db import migrations, models


def seed_device_categories(apps, schema_editor):
    DeviceCategory = apps.get_model('equipment', 'DeviceCategory')
    from equipment.categories import CATEGORY_CHOICES, IMPORT_PROFILE_BY_GROUP

    sort = 0
    for code, label, group in CATEGORY_CHOICES:
        sort += 1
        profile_key = IMPORT_PROFILE_BY_GROUP.get(group, 'machine')
        import_profile = 'it' if profile_key == 'it' else 'machine'
        DeviceCategory.objects.update_or_create(
            code=code,
            defaults={
                'name': label,
                'group': group,
                'import_profile': import_profile,
                'sort_order': sort,
                'is_active': True,
                'is_system': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0005_alter_device_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Mã loại')),
                ('name', models.CharField(max_length=200, verbose_name='Tên hiển thị')),
                ('group', models.CharField(max_length=30, verbose_name='Nhóm')),
                ('import_profile', models.CharField(
                    choices=[('it', 'IT (có Hostname, IP…)'), ('machine', 'Máy xưởng')],
                    default='machine', max_length=20, verbose_name='Mẫu import Excel',
                )),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('is_system', models.BooleanField(default=False, verbose_name='Loại hệ thống')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Loại thiết bị',
                'verbose_name_plural': 'Loại thiết bị',
                'ordering': ['group', 'sort_order', 'name'],
            },
        ),
        migrations.RunPython(seed_device_categories, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='device',
            name='category',
            field=models.CharField(db_index=True, default='PC', max_length=50, verbose_name='Loại thiết bị'),
        ),
    ]
