from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kiotviet', '0004_extended_sync_entities'),
    ]

    operations = [
        migrations.AddField(
            model_name='kvproduct',
            name='category_path',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
