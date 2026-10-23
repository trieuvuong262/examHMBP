from django.db import migrations


def copy_colorway_images(apps, schema_editor):
    from thiet_ke_sp.services.workflow import backfill_colorway_product_images

    backfill_colorway_product_images()


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0029_reopen_edit_step'),
        ('kho_san_pham', '0019_product_code_style_size'),
    ]

    operations = [
        migrations.RunPython(copy_colorway_images, migrations.RunPython.noop),
    ]
