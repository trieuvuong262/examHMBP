from django.db import migrations, models
from django.db.models import Count, Min


def normalize_and_dedupe(apps, schema_editor):
    SalaryAdvanceRequest = apps.get_model('utilities', 'SalaryAdvanceRequest')
    SalaryAdvanceDecline = apps.get_model('utilities', 'SalaryAdvanceDecline')

    for Model in (SalaryAdvanceRequest, SalaryAdvanceDecline):
        for row in Model.objects.all().only('id', 'request_month'):
            if row.request_month and row.request_month.day != 1:
                row.request_month = row.request_month.replace(day=1)
                row.save(update_fields=['request_month'])

        dupes = (
            Model.objects.values('employee_id', 'request_month')
            .annotate(cnt=Count('id'), keep_id=Min('id'))
            .filter(cnt__gt=1)
        )
        for d in dupes:
            Model.objects.filter(
                employee_id=d['employee_id'],
                request_month=d['request_month'],
            ).exclude(id=d['keep_id']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0008_portal_push_consent_log'),
    ]

    operations = [
        migrations.RunPython(normalize_and_dedupe, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='salaryadvancerequest',
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name='salaryadvancedecline',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='salaryadvancerequest',
            name='request_month',
            field=models.DateField(
                help_text='Mỗi tài khoản chỉ được ứng lương 1 lần trong một tháng.',
                verbose_name='Tháng ứng',
            ),
        ),
        migrations.AddConstraint(
            model_name='salaryadvancerequest',
            constraint=models.UniqueConstraint(
                fields=('employee', 'request_month'),
                name='utilities_salaryadvance_employee_month_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='salaryadvancedecline',
            constraint=models.UniqueConstraint(
                fields=('employee', 'request_month'),
                name='utilities_salarydecline_employee_month_uniq',
            ),
        ),
    ]
