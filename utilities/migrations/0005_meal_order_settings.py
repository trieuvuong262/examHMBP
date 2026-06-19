from datetime import time

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0004_meal_push'),
    ]

    operations = [
        migrations.CreateModel(
            name='MealOrderSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_start_time', models.TimeField(default=time(16, 0), verbose_name='Bắt đầu')),
                ('order_end_time', models.TimeField(default=time(20, 0), verbose_name='Kết thúc')),
                ('order_days_before', models.PositiveSmallIntegerField(
                    default=1,
                    help_text='1 = đặt vào ngày hôm trước ngày ăn',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(7),
                    ],
                    verbose_name='Số ngày trước ngày ăn',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Thiết lập đặt cơm',
                'verbose_name_plural': 'Thiết lập đặt cơm',
            },
        ),
    ]
