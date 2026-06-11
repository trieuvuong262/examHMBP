import django.db.models.deletion
from django.db import migrations, models


def set_stocktake_main_location(apps, schema_editor):
    Stocktake = apps.get_model('kho_npl', 'Stocktake')
    WarehouseLocation = apps.get_model('kho_npl', 'WarehouseLocation')
    main = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
    if not main:
        main = WarehouseLocation.objects.filter(is_active=True).order_by('id').first()
    if not main:
        return
    Stocktake.objects.filter(location__isnull=True).update(location_id=main.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0006_adjustment_lines'),
    ]

    operations = [
        migrations.AddField(
            model_name='stocktake',
            name='location',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='stocktakes',
                to='kho_npl.warehouselocation',
                verbose_name='Kho kiểm kê',
            ),
        ),
        migrations.RunPython(set_stocktake_main_location, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stocktake',
            name='location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='stocktakes',
                to='kho_npl.warehouselocation',
                verbose_name='Kho kiểm kê',
            ),
        ),
    ]
