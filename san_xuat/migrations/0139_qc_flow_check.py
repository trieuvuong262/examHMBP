import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0138_alter_sxteamdivisionmap_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SxQcFlowCheck',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_demo', models.BooleanField(db_index=True, default=False, verbose_name='Dữ liệu demo')),
                ('code', models.CharField(max_length=40, unique=True, verbose_name='Mã phiếu')),
                ('flow', models.CharField(
                    choices=[
                        ('inline', 'QC inline'),
                        ('endline', 'QC endline'),
                        ('preaudit', 'QC preaudit'),
                    ],
                    db_index=True,
                    max_length=20,
                    verbose_name='Luồng',
                )),
                ('product_code', models.CharField(blank=True, db_index=True, default='', max_length=60)),
                ('product_name', models.CharField(blank=True, default='', max_length=255)),
                ('team_slug', models.CharField(blank=True, db_index=True, default='', max_length=20, verbose_name='Tổ')),
                ('stage_name', models.CharField(blank=True, default='', max_length=120, verbose_name='Công đoạn')),
                ('checked_on', models.DateField(verbose_name='Ngày kiểm')),
                ('qty_lot', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Cỡ lô')),
                ('qty_checked', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL kiểm')),
                ('qty_pass', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL đạt')),
                ('qty_repair', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL sửa')),
                ('qty_fail', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='SL lỗi')),
                ('aql_level', models.DecimalField(decimal_places=2, default=Decimal('2.5'), max_digits=5, verbose_name='AQL (%)')),
                ('inspection_level', models.CharField(blank=True, default='II', max_length=5, verbose_name='Mức kiểm')),
                ('sample_size', models.PositiveIntegerField(default=0, verbose_name='Cỡ mẫu')),
                ('accept_qty', models.PositiveIntegerField(default=0, verbose_name='Số lỗi chấp nhận')),
                ('result', models.CharField(
                    choices=[
                        ('open', 'Chưa chốt'),
                        ('noted', 'Đã ghi'),
                        ('pass', 'Đạt'),
                        ('fail', 'Không đạt'),
                    ],
                    db_index=True,
                    default='open',
                    max_length=20,
                    verbose_name='Kết quả',
                )),
                ('status', models.CharField(
                    choices=[('draft', 'Nháp'), ('done', 'Đã chốt')],
                    db_index=True,
                    default='draft',
                    max_length=20,
                    verbose_name='Trạng thái',
                )),
                ('notes', models.TextField(blank=True, default='', verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='%(app_label)s_%(class)s_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('production_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='qc_flow_checks',
                    to='san_xuat.sxproductionorder',
                    verbose_name='Lệnh sản xuất',
                )),
            ],
            options={
                'verbose_name': 'Phiếu QC luồng',
                'verbose_name_plural': 'Phiếu QC luồng',
                'ordering': ['-checked_on', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='SxQcFlowDefectLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('defect_name', models.CharField(max_length=200, verbose_name='Lỗi')),
                ('severity', models.CharField(
                    choices=[('minor', 'Nhẹ'), ('major', 'Nặng'), ('critical', 'Nghiêm trọng')],
                    default='major',
                    max_length=20,
                    verbose_name='Mức',
                )),
                ('qty', models.DecimalField(decimal_places=2, default=Decimal('1'), max_digits=14, verbose_name='SL')),
                ('sheet', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='defect_lines',
                    to='san_xuat.sxqcflowcheck',
                )),
            ],
            options={
                'verbose_name': 'Lỗi trên phiếu QC luồng',
                'verbose_name_plural': 'Lỗi trên phiếu QC luồng',
                'ordering': ['id'],
            },
        ),
    ]
