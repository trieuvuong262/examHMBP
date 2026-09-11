from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0054_productionshiftproduct_efficiency_bonus_pct'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionshiftproduct',
            name='updated_by_2',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='production_products_updated_2',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cập nhật (người 2)',
            ),
        ),
        migrations.AddField(
            model_name='productionshiftproduct',
            name='manager_changed_fields',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Các khóa cột bị chỉnh: code, process, start, end, hours, quantity, damaged, norm.',
                verbose_name='Ô đã sửa bởi quản lý',
            ),
        ),
    ]
