# Generated manually — night auto-submit settings

from datetime import time
from decimal import Decimal

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0045_reportsgeneralsettings_expand'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reportsgeneralsettings',
            name='auto_submit_time',
            field=models.TimeField(
                default=time(23, 30),
                help_text='Giờ local trên VPS — cron chạy mỗi 5 phút trong cửa sổ grace.',
                verbose_name='Giờ tự động nộp ca sáng',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='night_auto_submit_enabled',
            field=models.BooleanField(default=True, verbose_name='Bật tự động nộp ca tối'),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='night_auto_submit_time',
            field=models.TimeField(
                default=time(5, 0),
                help_text='Thường sau khi ca tối kết thúc (~5h). Ngày BC = ngày bắt đầu 17h hôm trước.',
                verbose_name='Giờ tự động nộp ca tối',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='night_default_declared_work_hours',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('9.50'),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.01')),
                    django.core.validators.MaxValueValidator(Decimal('23.99')),
                ],
                verbose_name='Giờ làm việc mặc định ca tối',
            ),
        ),
    ]
