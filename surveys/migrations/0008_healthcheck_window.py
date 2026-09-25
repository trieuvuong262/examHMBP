from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0007_health_check'),
    ]

    operations = [
        migrations.AddField(
            model_name='healthcheckcampaign',
            name='opens_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Được cập nhật từ'),
        ),
        migrations.AddField(
            model_name='healthcheckcampaign',
            name='closes_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Được cập nhật đến'),
        ),
    ]
