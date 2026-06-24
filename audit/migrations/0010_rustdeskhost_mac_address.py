from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0009_rustdeskhost'),
    ]

    operations = [
        migrations.AddField(
            model_name='rustdeskhost',
            name='mac_address',
            field=models.CharField(blank=True, db_index=True, max_length=17, verbose_name='MAC (WoL)'),
        ),
    ]
