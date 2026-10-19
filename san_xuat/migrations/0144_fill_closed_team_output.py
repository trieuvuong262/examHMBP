# Generated manually

from django.db import migrations


def _fill_closed(apps, schema_editor):
    from san_xuat.services.team_progress_log import backfill_closed_team_outputs

    backfill_closed_team_outputs()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0143_retire_legacy_may_day_plans'),
    ]

    operations = [
        migrations.RunPython(_fill_closed, noop),
    ]
