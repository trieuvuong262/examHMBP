import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models

from kho_npl.choices import WAREHOUSE_SCRAP_CODE


def seed_scrap_warehouse(apps, schema_editor):
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')
    WarehouseLocation.objects.get_or_create(
        code=WAREHOUSE_SCRAP_CODE,
        defaults={'name': 'Kho hủy', 'is_active': True},
    )


def unseed_scrap_warehouse(apps, schema_editor):
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')
    WarehouseLocation.objects.filter(code=WAREHOUSE_SCRAP_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_npl', '0003_stock_transfer'),
    ]

    operations = [
        migrations.RunPython(seed_scrap_warehouse, unseed_scrap_warehouse),
        migrations.CreateModel(
            name='StockDisposal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu hủy')),
                ('disposal_date', models.DateField(verbose_name='Ngày hủy')),
                ('reason', models.CharField(
                    choices=[
                        ('damaged', 'Hư hỏng'),
                        ('defective', 'Lỗi chất lượng'),
                        ('expired', 'Hết hạn / quá hạn'),
                        ('other', 'Khác'),
                    ],
                    default='damaged',
                    max_length=30,
                    verbose_name='Lý do hủy',
                )),
                ('notes', models.TextField(blank=True, verbose_name='Ghi chú')),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Nháp'),
                        ('posted', 'Đã ghi sổ'),
                        ('cancelled', 'Đã hủy'),
                    ],
                    default='draft',
                    max_length=20,
                    verbose_name='Trạng thái',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('posted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='npl_disposals_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('from_location', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='disposals_out',
                    to='kho_npl.warehouselocation',
                    verbose_name='Kho nguồn',
                )),
                ('posted_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='npl_disposals_posted',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người ghi sổ',
                )),
            ],
            options={
                'verbose_name': 'Phiếu hủy',
                'verbose_name_plural': 'Phiếu hủy',
                'ordering': ['-disposal_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='StockDisposalLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(
                    decimal_places=3,
                    max_digits=14,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.001'))],
                    verbose_name='Số lượng',
                )),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='Ghi chú')),
                ('disposal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lines',
                    to='kho_npl.stockdisposal',
                    verbose_name='Phiếu hủy',
                )),
                ('material', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='disposal_lines',
                    to='kho_npl.material',
                    verbose_name='Nguyên phụ liệu',
                )),
            ],
            options={
                'verbose_name': 'Chi tiết phiếu hủy',
                'verbose_name_plural': 'Chi tiết phiếu hủy',
            },
        ),
    ]
