# Generated manually for SxGeneralSettings

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('san_xuat', '0019_hub_created_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxGeneralSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gate_release_before_issue', models.CharField(
                    choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                    default='block',
                    max_length=10,
                    verbose_name='Phát hành lệnh trước khi tạo yêu cầu xuất',
                )),
                ('gate_issue_before_stat', models.CharField(
                    choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                    default='block',
                    max_length=10,
                    verbose_name='Xuất kho (đã ghi sổ) trước khi xác nhận thống kê',
                )),
                ('gate_stat_before_fg', models.CharField(
                    choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                    default='block',
                    max_length=10,
                    verbose_name='Thống kê đã xác nhận trước khi nhập thành phẩm',
                )),
                ('gate_qc_pass_before_fg', models.CharField(
                    choices=[('off', 'Tắt — không kiểm tra'), ('warn', 'Cảnh báo — cho phép nhưng nhắc'), ('block', 'Chặn — bắt buộc đúng bước')],
                    default='block',
                    max_length=10,
                    verbose_name='Phiếu kiểm tra Đạt trước khi nhập thành phẩm',
                )),
                ('trace_min_timeline_events', models.PositiveSmallIntegerField(
                    default=4,
                    help_text='Nếu timeline ngắn hơn ngưỡng và checklist đủ, vẫn gợi ý kiểm tra chuỗi.',
                    verbose_name='Ngưỡng sự kiện timeline (Truy xuất — thiếu bước)',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Cập nhật bởi',
                )),
            ],
            options={
                'verbose_name': 'Thiết lập chung sản xuất',
                'verbose_name_plural': 'Thiết lập chung sản xuất',
            },
        ),
    ]
