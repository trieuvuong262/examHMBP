from django.db import migrations


def open_partner_tasks(apps, schema_editor):
    from thiet_ke_sp.services.workflow import backfill_partner_tasks

    backfill_partner_tasks()


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0024_role_partners'),
    ]

    operations = [
        migrations.RunPython(open_partner_tasks, migrations.RunPython.noop),
    ]
