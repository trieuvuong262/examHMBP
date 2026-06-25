from django.db import migrations


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0009_seed_odoo_training_library'),
    ]

    operations = [
        migrations.RunPython(noop, noop),
    ]
