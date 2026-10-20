from django.db import migrations, models


def seed_issue_reasons(apps, schema_editor):
    IssueReason = apps.get_model('kho_npl', 'IssueReason')
    defaults = [
        ('sample', 'Xuất làm mẫu', 10),
        ('waste', 'Xuất bù hao hụt', 20),
        ('return_supplier', 'Xuất trả nhà cung cấp', 30),
        ('scrap', 'Xuất hủy / hư hỏng', 40),
        ('transfer', 'Xuất điều chuyển kho', 50),
    ]
    for code, name, sort_order in defaults:
        IssueReason.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': sort_order, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0041_stockissue_route_link'),
    ]

    operations = [
        migrations.CreateModel(
            name='IssueReason',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=40, unique=True, verbose_name='Mã')),
                ('name', models.CharField(max_length=120, verbose_name='Lý do xuất')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
            ],
            options={
                'verbose_name': 'Lý do xuất',
                'verbose_name_plural': 'Lý do xuất',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RunPython(seed_issue_reasons, migrations.RunPython.noop),
    ]
