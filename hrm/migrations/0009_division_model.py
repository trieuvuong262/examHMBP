import django.db.models.deletion
from django.db import migrations, models

DEFAULT_DIVISIONS = [
    'QC',
    'Ép logo',
    'Giao Hàng',
    'HCNS',
    'Marketing',
    'Merchandise',
    'Thiết kế sản phẩm',
    'IE',
    'May mẫu',
    'Kế toán',
    'Kho nguyên phụ liệu',
    'Điều phối (Kiểm đếm xuất nhập hàng)',
]


def seed_and_migrate_divisions(apps, schema_editor):
    Division = apps.get_model('hrm', 'Division')
    Profile = apps.get_model('hrm', 'Profile')

    cache = {}
    for index, name in enumerate(DEFAULT_DIVISIONS):
        div, _ = Division.objects.get_or_create(
            name=name,
            defaults={'sort_order': index, 'is_active': True},
        )
        cache[name.lower()] = div

    for profile in Profile.objects.all():
        old_name = (getattr(profile, 'division_old', '') or '').strip()
        if not old_name:
            continue
        key = old_name.lower()
        if key not in cache:
            div, _ = Division.objects.get_or_create(
                name=old_name,
                defaults={'sort_order': 100, 'is_active': True},
            )
            cache[key] = div
        profile.division_id = cache[key].id
        profile.save(update_fields=['division_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0008_department_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='Division',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='Tên bộ phận')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang sử dụng')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')),
            ],
            options={
                'verbose_name': 'Bộ phận',
                'verbose_name_plural': 'Bộ phận',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RenameField(
            model_name='profile',
            old_name='division',
            new_name='division_old',
        ),
        migrations.AddField(
            model_name='profile',
            name='division',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='division_profiles',
                to='hrm.division',
                verbose_name='Bộ phận',
            ),
        ),
        migrations.RunPython(seed_and_migrate_divisions, noop),
        migrations.RemoveField(
            model_name='profile',
            name='division_old',
        ),
    ]
