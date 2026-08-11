from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0060_fg_receipt_received_by_warehouse'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxTeamWorkClose',
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
                ('closed_at', models.DateTimeField(auto_now_add=True, verbose_name='Lúc hoàn thành')),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(app_label)s_%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('production_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='team_work_closes',
                    to='san_xuat.sxproductionorder',
                    verbose_name='Lệnh sản xuất',
                )),
            ],
            options={
                'verbose_name': 'Chốt công việc tổ',
                'verbose_name_plural': 'Chốt công việc tổ',
                'ordering': ['-closed_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxteamworkclose',
            constraint=models.UniqueConstraint(
                fields=('production_order', 'team_slug'),
                name='san_xuat_team_work_close_mo_slug_uniq',
            ),
        ),
    ]
