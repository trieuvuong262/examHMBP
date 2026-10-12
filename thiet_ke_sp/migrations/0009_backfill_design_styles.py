from django.db import migrations
from django.db.models import F, Q


def forwards(apps, schema_editor):
    Handover = apps.get_model('thiet_ke_sp', 'Handover')
    ProductStyle = apps.get_model('kho_san_pham', 'ProductStyle')
    ProductType = apps.get_model('kho_san_pham', 'ProductType')

    Handover.objects.filter(tech_doc__isnull=False, transferred_at__isnull=True).update(
        transferred_at=F('handed_at'), transferred_by=F('handed_by'),
    )
    for h in Handover.objects.select_related('dossier'):
        code = (h.product_code or '').strip().upper()
        if not code:
            continue
        style = ProductStyle.objects.filter(code=code).first()
        if style:
            if style.source != 'design':
                style.source = 'design'
                style.save(update_fields=['source'])
            continue
        group = (h.dossier.product_group or '').strip().upper()
        if not group:
            continue
        types = list(ProductType.objects.filter(is_active=True).filter(
            Q(code=group) | Q(code__startswith=f'{group}-'))[:2])
        if len(types) != 1:
            continue
        ProductStyle.objects.create(
            code=code, product_type=types[0], name=(h.dossier.name or '')[:500],
            brand='JP', year=h.handed_at.year, source='design', is_active=True, created_by_id=h.handed_by_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0008_design_transfer'),
        ('kho_san_pham', '0017_design_transfer'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
