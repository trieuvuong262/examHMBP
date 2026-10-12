from django.db import migrations


def load(apps, schema_editor):
    from ra_mat_sp.defaults import load_default_checklist

    load_default_checklist(apps.get_model('ra_mat_sp', 'ChecklistTemplateItem'))


class Migration(migrations.Migration):
    dependencies = [
        ('ra_mat_sp', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(load, migrations.RunPython.noop),
    ]
