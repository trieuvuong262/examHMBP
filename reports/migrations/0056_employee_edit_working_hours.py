# Generated manually — employee edit deadline uses working hours

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0055_productionshiftproduct_manager_update_tracking'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reportsgeneralsettings',
            name='employee_edit_deadline_hours',
            field=models.PositiveSmallIntegerField(
                default=24,
                help_text='Giờ làm việc — không tính chiều thứ Bảy (từ 12:00) và Chủ nhật.',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(168),
                ],
                verbose_name='Thời hạn CN sửa sau nộp (giờ làm việc)',
            ),
        ),
    ]
