# Generated manually

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_san_pham', '0013_alter_stockledger_source_doc_type'),
        ('san_xuat', '0094_sxfgreceiptline_warehouse'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(max_length=40, unique=True, verbose_name='Mã phiếu nhập')),
                ('receipt_date', models.DateField(verbose_name='Ngày nhập')),
                ('status', models.CharField(choices=[('draft', 'Nháp'), ('posted', 'Đã nhập kho'), ('cancelled', 'Hủy')], db_index=True, default='posted', max_length=20, verbose_name='Trạng thái')),
                ('production_order_code', models.CharField(blank=True, default='', max_length=60, verbose_name='Lệnh SX')),
                ('product_code', models.CharField(blank=True, default='', max_length=80, verbose_name='Mã SP')),
                ('notes', models.TextField(blank=True, default='', verbose_name='Ghi chú')),
                ('posted_at', models.DateTimeField(blank=True, null=True, verbose_name='Nhập kho lúc')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kho_sp_receipts_created', to=settings.AUTH_USER_MODEL, verbose_name='Người tạo')),
                ('fg_receipt', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_receipts', to='san_xuat.sxfgreceiptrequest', verbose_name='Yêu cầu nhập TP')),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_receipts', to='kho_san_pham.warehouse', verbose_name='Kho nhập')),
            ],
            options={
                'verbose_name': 'Phiếu nhập kho thành phẩm',
                'verbose_name_plural': 'Phiếu nhập kho thành phẩm',
                'db_table': 'kho_sp_stock_receipt',
                'ordering': ['-receipt_date', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='StockReceiptLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Số lượng')),
                ('unit_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='Đơn giá')),
                ('size_label', models.CharField(blank=True, default='', max_length=40, verbose_name='Size')),
                ('color_label', models.CharField(blank=True, default='', max_length=40, verbose_name='Màu')),
                ('notes', models.CharField(blank=True, default='', max_length=255, verbose_name='Ghi chú')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_receipt_lines', to='kho_san_pham.product', verbose_name='SKU')),
                ('receipt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='kho_san_pham.stockreceipt', verbose_name='Phiếu nhập')),
            ],
            options={
                'verbose_name': 'Dòng phiếu nhập TP',
                'verbose_name_plural': 'Dòng phiếu nhập TP',
                'db_table': 'kho_sp_stock_receipt_line',
                'ordering': ['pk'],
            },
        ),
        migrations.AlterField(
            model_name='stockledger',
            name='source_doc_type',
            field=models.CharField(choices=[('fg_receipt', 'Yêu cầu nhập thành phẩm'), ('stock_receipt', 'Phiếu nhập kho thành phẩm'), ('invoice', 'Hóa đơn bán'), ('sale_return', 'Phiếu trả hàng'), ('transfer', 'Phiếu chuyển kho'), ('stocktake', 'Phiếu kiểm kê'), ('kv_onhand', 'Tồn KiotViet (cửa hàng)'), ('disposal', 'Phiếu hủy')], db_index=True, max_length=30, verbose_name='Loại chứng từ nguồn'),
        ),
    ]
