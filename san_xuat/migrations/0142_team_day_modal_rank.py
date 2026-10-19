from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0141_plan_team_keeps_department'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxTeamDayModalRank',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_slug', models.CharField(db_index=True, max_length=40, verbose_name='Slug tổ')),
                ('plan_date', models.DateField(db_index=True, verbose_name='Ngày')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('sales_order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='team_day_modal_ranks',
                    to='san_xuat.sxsalesorder',
                    verbose_name='Đơn đặt hàng',
                )),
            ],
            options={
                'verbose_name': 'Thứ tự đơn trong ngày tổ',
                'verbose_name_plural': 'Thứ tự đơn trong ngày tổ',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='sxteamdaymodalrank',
            constraint=models.UniqueConstraint(
                fields=('team_slug', 'plan_date', 'sales_order'),
                name='sx_team_day_modal_rank_uniq',
            ),
        ),
    ]
