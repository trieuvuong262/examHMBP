from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0039_seed_vat_tu_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='contact_name',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Người liên hệ'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='address',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Địa chỉ'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='tax_code',
            field=models.CharField(blank=True, default='', max_length=32, verbose_name='Mã số thuế'),
        ),
    ]
