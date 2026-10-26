from django.db import migrations


def sync(apps, schema_editor):
    from ra_mat_sp.defaults import load_default_checklist
    from ra_mat_sp.services import sync_checklist_to_open_plans

    load_default_checklist(apps.get_model('ra_mat_sp', 'ChecklistTemplateItem'))
    sync_checklist_to_open_plans()


class Migration(migrations.Migration):
    dependencies = [
        ('ra_mat_sp', '0003_group_owners'),
    ]

    operations = [
        migrations.RunPython(sync, migrations.RunPython.noop),
    ]
