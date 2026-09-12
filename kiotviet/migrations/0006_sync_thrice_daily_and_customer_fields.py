from django.db import migrations, models


ENTITY_ALL = [
    'branches',
    'categories',
    'users',
    'sale_channels',
    'locations',
    'bank_accounts',
    'surcharges',
    'customer_groups',
    'pricebooks',
    'products',
    'customers',
    'orders',
    'invoices',
    'purchase_orders',
    'transfers',
    'returns',
    'cashflow',
]

# 3 lần/ngày: 06:00, 12:00, 19:00
THRICE_DAILY = 481


def apply_thrice_daily_all_entities(apps, schema_editor):
    KvSyncConfig = apps.get_model('kiotviet', 'KvSyncConfig')
    for config in KvSyncConfig.objects.all():
        config.interval_minutes = THRICE_DAILY
        config.schedule_enabled = True
        config.enabled_entities = list(ENTITY_ALL)
        config.save(update_fields=['interval_minutes', 'schedule_enabled', 'enabled_entities'])


class Migration(migrations.Migration):

    dependencies = [
        ('kiotviet', '0005_product_category_path'),
    ]

    operations = [
        migrations.AlterField(
            model_name='kvbranch',
            name='contact_number',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AlterField(
            model_name='kvcustomer',
            name='contact_number',
            field=models.CharField(blank=True, db_index=True, default='', max_length=128),
        ),
        migrations.AlterField(
            model_name='kvcustomer',
            name='tax_code',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='kvsyncconfig',
            name='interval_minutes',
            field=models.PositiveSmallIntegerField(default=THRICE_DAILY),
        ),
        migrations.RunPython(apply_thrice_daily_all_entities, migrations.RunPython.noop),
    ]
