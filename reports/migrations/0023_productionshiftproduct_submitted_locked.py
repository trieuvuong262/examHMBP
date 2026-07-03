from django.db import migrations, models


def lock_existing_submitted_steps(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    ProductionShiftProduct = apps.get_model('reports', 'ProductionShiftProduct')
    submitted_ids = DailyWorkReport.objects.filter(status='SUBMITTED').values_list('pk', flat=True)
    ProductionShiftProduct.objects.filter(
        report_id__in=submitted_ids,
        status='DONE',
    ).update(submitted_locked=True)


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0022_reportcomment_is_read'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionshiftproduct',
            name='submitted_locked',
            field=models.BooleanField(
                default=False,
                help_text='True = không sửa sau khi đã gửi báo cáo (kể cả «Nhập tiếp»).',
                verbose_name='Đã chốt khi gửi báo cáo',
            ),
        ),
        migrations.RunPython(lock_existing_submitted_steps, migrations.RunPython.noop),
    ]
