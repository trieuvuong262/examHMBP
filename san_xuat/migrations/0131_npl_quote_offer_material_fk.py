# Generated manually for NPL quote ↔ kho_npl.Material link

import django.db.models.deletion
from django.db import migrations, models


def link_or_clear_offers(apps, schema_editor):
    Offer = apps.get_model('san_xuat', 'SxNplQuoteOffer')
    Material = apps.get_model('kho_npl', 'Material')
    by_code = {
        (m.code or '').strip().casefold(): m.pk
        for m in Material.objects.filter(is_active=True)
        if (m.code or '').strip()
    }
    for offer in Offer.objects.all():
        key = (offer.material_code or '').strip().casefold()
        mat_id = by_code.get(key)
        if mat_id:
            offer.material_id = mat_id
            offer.save(update_fields=['material_id'])
        else:
            offer.delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('kho_npl', '0040_supplier_order_contact'),
        ('san_xuat', '0130_npl_price_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxnplquoteoffer',
            name='material',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='npl_quote_offers',
                to='kho_npl.material',
                verbose_name='NPL (kho)',
            ),
        ),
        migrations.RunPython(link_or_clear_offers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='sxnplquoteoffer',
            name='material',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='npl_quote_offers',
                to='kho_npl.material',
                verbose_name='NPL (kho)',
            ),
        ),
    ]
