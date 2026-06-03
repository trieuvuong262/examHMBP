from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0032_division_department'),
    ]

    operations = [
        migrations.CreateModel(
            name='DivisionPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Tên vị trí')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang sử dụng')),
                ('department', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='division_positions',
                    to='hrm.department',
                    verbose_name='Phòng ban',
                )),
                ('division', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='positions',
                    to='hrm.division',
                    verbose_name='Bộ phận',
                )),
            ],
            options={
                'verbose_name': 'Vị trí (bộ phận)',
                'verbose_name_plural': 'Vị trí (bộ phận)',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='divisionposition',
            constraint=models.UniqueConstraint(
                fields=('division', 'name'),
                name='hrm_division_position_div_name_uniq',
            ),
        ),
    ]
