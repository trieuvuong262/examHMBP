import django.core.validators
from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0040_supplier_order_contact'),
        ('san_xuat', '0126_sxsalesorderline_suggest_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxnplpurchaserequest',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('transfer', 'Chuyển khoản'),
                    ('cash', 'Tiền mặt'),
                    ('credit', 'Công nợ'),
                ],
                default='',
                max_length=20,
                verbose_name='Hình thức thanh toán',
            ),
        ),
        migrations.AddField(
            model_name='sxnplpurchaserequestline',
            name='supplier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='npl_purchase_request_lines',
                to='kho_npl.supplier',
                verbose_name='Nhà cung cấp',
            ),
        ),
        migrations.AddField(
            model_name='sxnplpurchaserequestline',
            name='unit_price',
            field=models.DecimalField(
                decimal_places=6,
                default=Decimal('0'),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='Đơn giá',
            ),
        ),
        migrations.AddField(
            model_name='sxnplpurchaserequestline',
            name='expected_date',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày giao'),
        ),
        migrations.AddField(
            model_name='sxnplpurchaserequestline',
            name='payment_method',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Thanh toán'),
        ),
        migrations.AddField(
            model_name='sxnplpurchaserequestline',
            name='notes',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Ghi chú'),
        ),
        migrations.AddField(
            model_name='sxpurchaseorder',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('transfer', 'Chuyển khoản'),
                    ('cash', 'Tiền mặt'),
                    ('credit', 'Công nợ'),
                ],
                default='',
                max_length=20,
                verbose_name='Hình thức thanh toán',
            ),
        ),
        migrations.AddField(
            model_name='sxpurchaseorder',
            name='order_date',
            field=models.DateField(blank=True, null=True, verbose_name='Ngày đặt'),
        ),
        migrations.AddField(
            model_name='sxpurchaseorderline',
            name='notes',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Ghi chú'),
        ),
    ]
