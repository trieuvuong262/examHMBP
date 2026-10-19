# Generated manually

from django.db import migrations


def _retire_may(apps, schema_editor):
    from san_xuat.services.team_output_report import retire_legacy_may_day_plans

    retire_legacy_may_day_plans()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0142_team_day_modal_rank'),
    ]

    operations = [
        migrations.RunPython(_retire_may, noop),
    ]
