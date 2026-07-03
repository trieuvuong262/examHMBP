"""Gộp báo cáo tăng ca (OVERTIME) vào ca sáng."""

from django.db import migrations


def merge_overtime_into_morning(apps, schema_editor):
    DailyWorkReport = apps.get_model('reports', 'DailyWorkReport')
    ProductionShiftProduct = apps.get_model('reports', 'ProductionShiftProduct')

    overtime_reports = DailyWorkReport.objects.filter(
        shift='OVERTIME',
        report_profile='production',
    ).order_by('report_date', 'employee_id')

    for ot in overtime_reports:
        morning = DailyWorkReport.objects.filter(
            employee_id=ot.employee_id,
            report_date=ot.report_date,
            report_profile=ot.report_profile,
            report_period=ot.report_period,
            shift='MORNING',
        ).first()
        if morning:
            max_order = ProductionShiftProduct.objects.filter(report_id=morning.id).count()
            for offset, product in enumerate(
                ProductionShiftProduct.objects.filter(report_id=ot.id).order_by('sort_order', 'id')
            ):
                product.report_id = morning.id
                product.sort_order = max_order + offset
                product.save(update_fields=['report_id', 'sort_order'])
            ot.delete()
        else:
            ot.shift = 'MORNING'
            ot.save(update_fields=['shift'])


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0023_productionshiftproduct_submitted_locked'),
    ]

    operations = [
        migrations.RunPython(merge_overtime_into_morning, migrations.RunPython.noop),
    ]
