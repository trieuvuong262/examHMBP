from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='useractivitylog',
            name='machine_name',
            field=models.CharField(blank=True, db_index=True, max_length=128, verbose_name='Tên máy'),
        ),
        migrations.AlterField(
            model_name='useractivitylog',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True, verbose_name='IP local'),
        ),
    ]
