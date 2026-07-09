from django.db import migrations


def clear_bulk_proxy_updated_by(apps, schema_editor):
    """Reset cột updated_by — trước đây bị gán hàng loạt khi lưu nhập hộ."""
    ProductionShiftProduct = apps.get_model('reports', 'ProductionShiftProduct')
    ProductionShiftProduct.objects.filter(updated_by_id__isnull=False).update(
        updated_by_id=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0037_dailyworkreporteditlog_detail'),
    ]

    operations = [
        migrations.RunPython(clear_bulk_proxy_updated_by, migrations.RunPython.noop),
    ]
