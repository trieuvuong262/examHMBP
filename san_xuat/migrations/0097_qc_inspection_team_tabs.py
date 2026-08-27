# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0096_sxqcrequest_team_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxqcinspectioncriterialine',
            name='team_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='cat / inep / theu / may / ht / gh — tab tiêu chuẩn trên phiếu.',
                max_length=20,
                verbose_name='Tổ',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='sxqcinspectioncriterialine',
            unique_together={('inspection', 'criteria', 'team_slug')},
        ),
        migrations.CreateModel(
            name='SxQcInspectionTeamResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_slug', models.CharField(db_index=True, max_length=20, verbose_name='Tổ')),
                ('qty_pass', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('qty_fail', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('result', models.CharField(
                    choices=[('pass', 'Đạt'), ('fail', 'Không đạt'), ('pending', 'Chờ')],
                    default='pending',
                    max_length=20,
                )),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('inspection', models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name='team_results',
                    to='san_xuat.sxqcinspection',
                )),
            ],
            options={
                'verbose_name': 'Kết quả QC theo tổ',
                'verbose_name_plural': 'Kết quả QC theo tổ',
                'ordering': ['id'],
                'unique_together': {('inspection', 'team_slug')},
            },
        ),
    ]
