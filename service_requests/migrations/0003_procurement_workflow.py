# Generated manually for procurement workflow refactor

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0002_seed_asset_workflow'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecurringItemCatalog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Tên hàng')),
                ('description', models.TextField(blank=True, verbose_name='Mô tả')),
                ('unit', models.CharField(default='cái', max_length=50, verbose_name='Đơn vị')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recurring_catalog_items', to=settings.AUTH_USER_MODEL, verbose_name='Người tạo')),
            ],
            options={
                'verbose_name': 'Hàng mua định kỳ',
                'verbose_name_plural': 'Danh mục hàng mua định kỳ',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='advance_amount',
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=14, null=True, verbose_name='Số tiền tạm ứng'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='approval_tier',
            field=models.CharField(blank=True, choices=[('none', 'Không cần duyệt cấp cao'), ('accountant', 'Kế toán'), ('director', 'Giám đốc')], max_length=20, verbose_name='Cấp duyệt chi phí'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='goods_receiver',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='received_service_requests', to=settings.AUTH_USER_MODEL, verbose_name='Người nhận hàng'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='is_from_catalog',
            field=models.BooleanField(default=False, verbose_name='Từ danh mục định kỳ'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='needs_advance',
            field=models.BooleanField(default=False, verbose_name='Cần tạm ứng'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='recurring_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requests', to='service_requests.recurringitemcatalog', verbose_name='Hàng định kỳ'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='selected_total_amount',
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=14, null=True, verbose_name='Tổng NCC đã chọn'),
        ),
        migrations.AddField(
            model_name='servicerequeststep',
            name='step_code',
            field=models.CharField(blank=True, db_index=True, max_length=40, verbose_name='Mã bước'),
        ),
        migrations.AlterField(
            model_name='requesttypesteptemplate',
            name='assignee_rule',
            field=models.CharField(choices=[('direct_manager', 'Cấp trên trực tiếp'), ('department_queue', 'Hàng đợi phòng ban'), ('director', 'Giám đốc')], max_length=30, verbose_name='Quy tắc gán người xử lý'),
        ),
        migrations.CreateModel(
            name='ProcurementLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=500, verbose_name='Mô tả hàng hóa')),
                ('quantity_requested', models.DecimalField(decimal_places=2, default=1, max_digits=12, verbose_name='SL đề xuất')),
                ('quantity_confirmed', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='SL xác nhận')),
                ('unit', models.CharField(default='cái', max_length=50, verbose_name='Đơn vị')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('recurring_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='line_items', to='service_requests.recurringitemcatalog', verbose_name='Hàng định kỳ')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='service_requests.servicerequest', verbose_name='Yêu cầu')),
            ],
            options={
                'verbose_name': 'Dòng hàng mua',
                'verbose_name_plural': 'Dòng hàng mua',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='ProcurementSupplierQuote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier_name', models.CharField(max_length=200, verbose_name='Nhà cung cấp')),
                ('unit_price', models.DecimalField(decimal_places=0, max_digits=14, verbose_name='Đơn giá (VNĐ)')),
                ('quote_file', models.FileField(blank=True, upload_to='service_requests/quotes/%Y/%m/', verbose_name='File báo giá')),
                ('is_selected', models.BooleanField(default=False, verbose_name='Được chọn')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('line_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quotes', to='service_requests.procurementlineitem', verbose_name='Dòng hàng')),
            ],
            options={
                'verbose_name': 'Báo giá NCC',
                'verbose_name_plural': 'Báo giá NCC',
                'ordering': ['pk'],
            },
        ),
    ]
