# Generated manually for SxTeamDivisionMap

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrm', '0089_seed_san_xuat_team_work_menus'),
        ('san_xuat', '0058_sales_order_line_bom_routing'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxTeamDivisionMap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_demo', models.BooleanField(db_index=True, default=False, verbose_name='Dữ liệu demo')),
                ('team_slug', models.CharField(
                    choices=[
                        ('cat', 'Cắt'),
                        ('inep', 'In - Ép'),
                        ('theu', 'Thêu'),
                        ('may', 'May'),
                        ('ht', 'Ủi - Gấp xếp'),
                        ('gh', 'Giao hàng thành phẩm'),
                    ],
                    db_index=True,
                    max_length=20,
                    verbose_name='Tổ chuyền',
                )),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(app_label)s_%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('division', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sx_team_maps',
                    to='hrm.division',
                    verbose_name='Bộ phận (HR)',
                )),
            ],
            options={
                'verbose_name': 'Map bộ phận → tổ chuyền',
                'verbose_name_plural': 'Map bộ phận → tổ chuyền',
                'ordering': ['team_slug', 'division__sort_order', 'division__name'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxteamdivisionmap',
            constraint=models.UniqueConstraint(
                fields=('division',),
                name='san_xuat_team_division_map_division_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='sxteamdivisionmap',
            constraint=models.UniqueConstraint(
                fields=('team_slug', 'division'),
                name='san_xuat_team_division_map_slug_div_uniq',
            ),
        ),
    ]
