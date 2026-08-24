"""Thời gian trung gian mặc định theo cặp bộ phận (Cắt→May ≠ May→Ủi)."""

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0089_alter_processstep_count_minutes_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SxInterStepHop',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_slug', models.CharField(choices=[('cat', 'Cắt'), ('inep', 'In - Ép'), ('theu', 'Thêu'), ('may', 'May'), ('ht', 'Ủi - Gấp xếp'), ('gh', 'Giao hàng thành phẩm')], db_index=True, max_length=20, verbose_name='Từ bộ phận')),
                ('to_slug', models.CharField(choices=[('cat', 'Cắt'), ('inep', 'In - Ép'), ('theu', 'Thêu'), ('may', 'May'), ('ht', 'Ủi - Gấp xếp'), ('gh', 'Giao hàng thành phẩm')], db_index=True, max_length=20, verbose_name='Đến bộ phận')),
                ('count_minutes', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='Kiểm đếm (phút)')),
                ('transfer_minutes', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='Vận chuyển (phút)')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Cập nhật bởi')),
            ],
            options={
                'verbose_name': 'Thời gian trung gian theo cặp bộ phận',
                'verbose_name_plural': 'Thời gian trung gian theo cặp bộ phận',
                'ordering': ['from_slug', 'to_slug'],
                'constraints': [models.UniqueConstraint(fields=('from_slug', 'to_slug'), name='san_xuat_inter_step_hop_pair_uniq'), models.CheckConstraint(condition=models.Q(('from_slug', models.F('to_slug')), _negated=True), name='san_xuat_inter_step_hop_diff_slug')],
            },
        ),
    ]
