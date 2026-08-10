from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0054_alter_sxworkcenter_team_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsalesorderline',
            name='size_qtys',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Ví dụ {"S": 100, "M": 200}',
                verbose_name='SL theo size',
            ),
        ),
    ]
