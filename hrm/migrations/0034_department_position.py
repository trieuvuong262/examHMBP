from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0033_division_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentPosition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Tên vị trí')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang sử dụng')),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='department_positions',
                    to='hrm.department',
                    verbose_name='Phòng ban',
                )),
            ],
            options={
                'verbose_name': 'Vị trí (phòng ban)',
                'verbose_name_plural': 'Vị trí (phòng ban)',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='departmentposition',
            constraint=models.UniqueConstraint(
                fields=('department', 'name'),
                name='hrm_department_position_dept_name_uniq',
            ),
        ),
    ]
