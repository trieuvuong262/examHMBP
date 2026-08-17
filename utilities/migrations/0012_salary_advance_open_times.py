# Generated manually for open_time_start / open_time_end

import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0011_salary_advance_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='salaryadvancesettings',
            name='open_time_start',
            field=models.TimeField(
                default=datetime.time(0, 0),
                help_text='Giờ phút bắt đầu mở ứng vào ngày bắt đầu.',
                verbose_name='Giờ bắt đầu',
            ),
        ),
        migrations.AddField(
            model_name='salaryadvancesettings',
            name='open_time_end',
            field=models.TimeField(
                default=datetime.time(23, 59),
                help_text='Giờ phút đóng ứng vào ngày kết thúc.',
                verbose_name='Giờ kết thúc',
            ),
        ),
    ]
