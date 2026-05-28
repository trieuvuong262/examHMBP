from django.db import migrations, models


def dedupe_kpi_periods(apps, schema_editor):
    KpiPeriod = apps.get_model('kpi', 'KpiPeriod')
    labels = {
        'Q1': 'Quý 1', 'Q2': 'Quý 2', 'Q3': 'Quý 3', 'Q4': 'Quý 4',
        'H1': 'Sáu tháng đầu năm (H1)', 'H2': 'Sáu tháng cuối năm (H2)', 'Y': 'Cả năm (Y)',
    }
    seen = set()
    for period in KpiPeriod.objects.order_by('year', 'period_type', 'id'):
        key = (period.year, period.period_type)
        if key in seen:
            period.delete()
        else:
            seen.add(key)
            if not period.title:
                period.title = labels.get(period.period_type, period.period_type)
                period.save(update_fields=['title'])


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0005_alter_yearlykpi_h1_status_alter_yearlykpi_h2_status_and_more'),
    ]

    operations = [
        migrations.RunPython(dedupe_kpi_periods, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='kpiperiod',
            constraint=models.UniqueConstraint(
                fields=('year', 'period_type'),
                name='kpi_kpiperiod_year_period_type_uniq',
            ),
        ),
    ]
