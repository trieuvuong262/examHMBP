from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kpi', '0007_monthly_kpi'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlykpiitem',
            name='level_improve',
            field=models.TextField(blank=True, default='', verbose_name='Mức cần cải thiện'),
        ),
    ]
