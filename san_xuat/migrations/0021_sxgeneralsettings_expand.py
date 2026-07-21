# Generated manually — mở rộng SxGeneralSettings (Cao + Trung)

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0020_sxgeneralsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='gate_open_qc_alert_before_fg',
            field=models.CharField(
                choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                default='block',
                max_length=10,
                verbose_name='Cảnh báo chất lượng đang mở trước khi nhập thành phẩm',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='gate_packing_before_done',
            field=models.CharField(
                choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                default='off',
                max_length=10,
                verbose_name='Đóng gói đã xác nhận trước khi hoàn thành lệnh',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='auto_create_qc_from_stat',
            field=models.BooleanField(default=True, verbose_name='Tự tạo yêu cầu kiểm tra khi xác nhận thống kê'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='auto_create_defect_alert',
            field=models.BooleanField(default=True, verbose_name='Tự tạo cảnh báo khi tỷ lệ lỗi vượt ngưỡng'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='default_defect_tolerance_pct',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('5'), max_digits=6,
                help_text='Dùng khi sản phẩm chưa gắn bộ tiêu chuẩn QC.',
                verbose_name='Dung sai tỷ lệ lỗi mặc định (%)',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='default_sample_qty',
            field=models.PositiveIntegerField(
                default=5,
                help_text='Khi chưa chọn phương pháp lấy mẫu.',
                verbose_name='Số lượng mẫu mặc định',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='capacity_load_warn_pct',
            field=models.PositiveSmallIntegerField(default=80, verbose_name='Ngưỡng cảnh báo tải năng lực (%)'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='capacity_load_danger_pct',
            field=models.PositiveSmallIntegerField(default=100, verbose_name='Ngưỡng quá tải năng lực (%)'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='list_default_date_range_days',
            field=models.PositiveSmallIntegerField(default=7, verbose_name='Số ngày lọc danh sách mặc định'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='ycx_auto_reserve_stock',
            field=models.BooleanField(default=True, verbose_name='Giữ chỗ tồn khi tạo yêu cầu xuất vật tư'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='require_kv_link_for_fg_done',
            field=models.BooleanField(
                default=True,
                help_text='Tắt = gửi yêu cầu nhập thành phẩm có thể đánh dấu hoàn thành không cần KV.',
                verbose_name='Bắt buộc liên kết phiếu nhập KiotViet để hoàn tất nhập thành phẩm',
            ),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='shopfloor_auto_confirm_stat',
            field=models.BooleanField(default=True, verbose_name='Shop floor: quét xong tự xác nhận thống kê'),
        ),
        migrations.AddField(
            model_name='sxgeneralsettings',
            name='shopfloor_default_qty_good',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('1'), max_digits=14,
                verbose_name='Shop floor: số lượng đạt mặc định mỗi lần quét',
            ),
        ),
    ]
