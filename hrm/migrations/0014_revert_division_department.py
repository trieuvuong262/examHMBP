import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0013_division_department'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='division',
            name='hrm_division_department_name_uniq',
        ),
        migrations.RemoveField(
            model_name='division',
            name='department',
        ),
        migrations.AlterField(
            model_name='division',
            name='name',
            field=models.CharField(max_length=150, unique=True, verbose_name='Tên bộ phận'),
        ),
    ]
