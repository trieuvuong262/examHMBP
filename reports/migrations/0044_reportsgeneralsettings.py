# Generated manually — ReportsGeneralSettings singleton

from datetime import time

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_singleton(apps, schema_editor):
    ReportsGeneralSettings = apps.get_model('reports', 'ReportsGeneralSettings')
    ReportsGeneralSettings.objects.get_or_create(pk=1)


def unseed_singleton(apps, schema_editor):
    ReportsGeneralSettings = apps.get_model('reports', 'ReportsGeneralSettings')
    ReportsGeneralSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0043_alter_auto_submitted_help_text'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportsGeneralSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'workers_may_edit_stage_time',
                    models.BooleanField(default=True, verbose_name='Công nhân được sửa thời gian công đoạn'),
                ),
                (
                    'managers_may_edit_stage_time',
                    models.BooleanField(default=True, verbose_name='Quản lý được sửa thời gian công đoạn'),
                ),
                (
                    'auto_submit_time',
                    models.TimeField(
                        default=time(23, 30),
                        help_text='Giờ local trên VPS — cron chạy mỗi 5 phút trong cửa sổ grace.',
                        verbose_name='Giờ tự động nộp báo cáo',
                    ),
                ),
                (
                    'approve_deadline_hours',
                    models.PositiveSmallIntegerField(
                        default=24,
                        help_text='Sau khi nộp — hạn SLA duyệt (badge quá hạn). Quản lý vẫn duyệt được đến hạn không duyệt.',
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(168),
                        ],
                        verbose_name='Thời hạn duyệt (giờ)',
                    ),
                ),
                (
                    'unapprove_deadline_days',
                    models.PositiveSmallIntegerField(
                        default=7,
                        help_text='Số ngày sau khi duyệt mà quản lý còn được hoàn duyệt.',
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(90),
                        ],
                        verbose_name='Thời hạn hoàn duyệt (ngày)',
                    ),
                ),
                (
                    'auto_reject_deadline_hours',
                    models.PositiveSmallIntegerField(
                        default=24,
                        help_text='Sau khi nộp — quá hạn tự chuyển «Không duyệt». Cũng là hạn CN sửa sau nộp.',
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(168),
                        ],
                        verbose_name='Thời hạn không duyệt (giờ)',
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Cập nhật bởi',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Thiết lập chung báo cáo',
                'verbose_name_plural': 'Thiết lập chung báo cáo',
            },
        ),
        migrations.RunPython(seed_singleton, unseed_singleton),
    ]
