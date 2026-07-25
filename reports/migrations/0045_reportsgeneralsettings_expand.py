# Generated manually — expand ReportsGeneralSettings

from decimal import Decimal

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0044_reportsgeneralsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='employee_edit_deadline_hours',
            field=models.PositiveSmallIntegerField(
                default=24,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(168),
                ],
                verbose_name='Thời hạn CN sửa sau nộp (giờ)',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='default_declared_work_hours',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('9.50'),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.01')),
                    django.core.validators.MaxValueValidator(Decimal('23.99')),
                ],
                verbose_name='Giờ làm việc mặc định khi tự nộp',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='work_hours_min',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('7.50'),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.01')),
                    django.core.validators.MaxValueValidator(Decimal('23.99')),
                ],
                verbose_name='Giờ làm việc tối thiểu',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='work_hours_max',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('16.00'),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.01')),
                    django.core.validators.MaxValueValidator(Decimal('24.00')),
                ],
                verbose_name='Giờ làm việc tối đa (không gồm)',
            ),
        ),
        migrations.AddField(
            model_name='reportsgeneralsettings',
            name='auto_approve_proxy_reports',
            field=models.BooleanField(
                default=True,
                verbose_name='Tự duyệt báo cáo nhập hộ toàn bộ',
            ),
        ),
        migrations.AlterField(
            model_name='reportsgeneralsettings',
            name='auto_reject_deadline_hours',
            field=models.PositiveSmallIntegerField(
                default=24,
                help_text='Sau khi nộp — quá hạn tự chuyển «Không duyệt».',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(168),
                ],
                verbose_name='Thời hạn không duyệt (giờ)',
            ),
        ),
    ]
