# Generated manually

from django.db import migrations


def seed_team_criteria(apps, schema_editor):
    from san_xuat.services.qc import seed_default_team_qc_criteria

    seed_default_team_qc_criteria()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0098_qc_criteria_team_slug'),
    ]

    operations = [
        migrations.RunPython(seed_team_criteria, noop),
    ]
