from django.db import migrations, models
import django.db.models.deletion


def copy_disposal_location_to_lines(apps, schema_editor):
    StockDisposal = apps.get_model('kho_npl', 'StockDisposal')
    StockDisposalLine = apps.get_model('kho_npl', 'StockDisposalLine')
    for disposal in StockDisposal.objects.all().iterator():
        if not disposal.from_location_id:
            continue
        StockDisposalLine.objects.filter(disposal_id=disposal.pk).update(
            location_id=disposal.from_location_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('kho_npl', '0014_alter_stockissue_status_alter_stockreceipt_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockdisposalline',
            name='location',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='disposal_lines',
                to='kho_npl.warehouselocation',
                verbose_name='Vị trí kho',
            ),
        ),
        migrations.RunPython(copy_disposal_location_to_lines, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stockdisposalline',
            name='location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='disposal_lines',
                to='kho_npl.warehouselocation',
                verbose_name='Vị trí kho',
            ),
        ),
        migrations.RemoveField(
            model_name='stockdisposal',
            name='from_location',
        ),
    ]
