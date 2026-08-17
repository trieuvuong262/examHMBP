from django.db import migrations


def forwards_seconds_only(apps, schema_editor):
    SxSmvBasis = apps.get_model('san_xuat', 'SxSmvBasis')
    SxOperation = apps.get_model('san_xuat', 'SxOperation')

    sec, _ = SxSmvBasis.objects.get_or_create(
        code='SEC',
        defaults={'name': 'Giây', 'sort_order': 10, 'is_active': True},
    )
    if sec.name != 'Giây' or not sec.is_active or sec.sort_order != 10:
        sec.name = 'Giây'
        sec.is_active = True
        sec.sort_order = 10
        sec.save(update_fields=['name', 'is_active', 'sort_order'])

    SxSmvBasis.objects.exclude(code='SEC').update(is_active=False)
    SxOperation.objects.exclude(smv_basis='Giây').update(smv_basis='Giây')


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0077_sxoperation_approved_user'),
    ]

    operations = [
        migrations.RunPython(forwards_seconds_only, backwards_noop),
    ]
