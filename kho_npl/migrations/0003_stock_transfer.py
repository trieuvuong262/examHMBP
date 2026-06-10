import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_npl', '0002_seed_master_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu chuyển')),
                ('transfer_date', models.DateField(verbose_name='Ngày chuyển')),
                ('notes', models.TextField(blank=True, verbose_name='Ghi chú')),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Nháp'),
                        ('in_transit', 'Đang chuyển'),
                        ('received', 'Đã nhập'),
                        ('cancelled', 'Đã hủy'),
                    ],
                    default='draft',
                    max_length=20,
                    verbose_name='Trạng thái',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='npl_transfers_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo',
                )),
                ('from_location', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='transfers_out',
                    to='kho_npl.warehouselocation',
                    verbose_name='Kho gửi',
                )),
                ('received_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='npl_transfers_received',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người nhận',
                )),
                ('sent_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='npl_transfers_sent',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người gửi',
                )),
                ('to_location', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='transfers_in',
                    to='kho_npl.warehouselocation',
                    verbose_name='Kho nhận',
                )),
            ],
            options={
                'verbose_name': 'Phiếu chuyển kho',
                'verbose_name_plural': 'Phiếu chuyển kho',
                'ordering': ['-transfer_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='StockTransferLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(
                    decimal_places=3,
                    max_digits=14,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.001'))],
                    verbose_name='Số lượng',
                )),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='Ghi chú')),
                ('material', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='transfer_lines',
                    to='kho_npl.material',
                    verbose_name='Nguyên phụ liệu',
                )),
                ('transfer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lines',
                    to='kho_npl.stocktransfer',
                    verbose_name='Phiếu chuyển',
                )),
            ],
            options={
                'verbose_name': 'Chi tiết phiếu chuyển',
                'verbose_name_plural': 'Chi tiết phiếu chuyển',
            },
        ),
    ]
