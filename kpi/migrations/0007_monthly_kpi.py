from django.db import migrations, models
import django.db.models.deletion
import kpi.models


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0006_kpiperiod_unique_year_period_type'),
        migrations.swappable_dependency('auth.User'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyKpi',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField(default=kpi.models.current_year, verbose_name='Năm')),
                ('month', models.PositiveSmallIntegerField(default=kpi.models.current_month, verbose_name='Tháng')),
                ('imported_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('direct_manager', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='managed_monthly_kpis',
                    to='auth.user',
                    verbose_name='Quản lý',
                )),
                ('employee', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='monthly_kpis',
                    to='auth.user',
                    verbose_name='Nhân viên',
                )),
                ('imported_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='imported_monthly_kpis',
                    to='auth.user',
                )),
            ],
            options={
                'verbose_name': 'KPI tháng',
                'verbose_name_plural': 'KPI tháng',
                'ordering': ['-year', '-month', 'employee_id'],
            },
        ),
        migrations.CreateModel(
            name='MonthlyKpiItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=1)),
                ('work_group', models.CharField(blank=True, default='', max_length=255, verbose_name='Nhóm công việc')),
                ('weightage', models.FloatField(default=0.0, verbose_name='Trọng số')),
                ('indicator', models.TextField(verbose_name='Tiêu chí đo lường')),
                ('level_fail', models.TextField(blank=True, default='', verbose_name='Mức chưa đạt')),
                ('level_pass', models.TextField(blank=True, default='', verbose_name='Mức đạt')),
                ('level_exceed', models.TextField(blank=True, default='', verbose_name='Mức vượt')),
                ('self_actual', models.TextField(blank=True, default='', verbose_name='Đánh giá thực tế (NV)')),
                ('self_score', models.FloatField(blank=True, null=True, verbose_name='Điểm NV')),
                ('mgr_actual', models.TextField(blank=True, default='', verbose_name='Đánh giá thực tế (QL)')),
                ('mgr_score', models.FloatField(blank=True, null=True, verbose_name='Điểm QL')),
                ('monthly_kpi', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='kpi.monthlykpi',
                )),
            ],
            options={
                'verbose_name': 'Tiêu chí KPI tháng',
                'verbose_name_plural': 'Tiêu chí KPI tháng',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='monthlykpi',
            constraint=models.UniqueConstraint(
                fields=('employee', 'year', 'month'),
                name='kpi_monthlykpi_employee_year_month_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='monthlykpi',
            constraint=models.CheckConstraint(
                condition=models.Q(('month__gte', 1), ('month__lte', 12)),
                name='kpi_monthlykpi_month_1_12',
            ),
        ),
        migrations.DeleteModel(name='YearlyKpiItem'),
        migrations.DeleteModel(name='YearlyKpi'),
        migrations.DeleteModel(name='KpiPeriod'),
    ]
