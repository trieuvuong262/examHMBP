from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0009_backfill_design_styles'),
    ]

    operations = [
        migrations.AddField(
            model_name='modulesetting',
            name='default_roles',
            field=models.JSONField(blank=True, default=dict, verbose_name='Danh sách nhân sự phụ trách'),
        ),
    ]
