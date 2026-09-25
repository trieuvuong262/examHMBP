from datetime import datetime

from django.db import migrations
from django.utils import timezone


def set_window(apps, schema_editor):
    HealthCheckCampaign = apps.get_model('surveys', 'HealthCheckCampaign')
    tz = timezone.get_current_timezone()
    HealthCheckCampaign.objects.filter(code='ksk-2026-10').update(
        opens_at=timezone.make_aware(datetime(2026, 9, 25, 0, 0), tz),
        closes_at=timezone.make_aware(datetime(2026, 9, 26, 17, 0), tz),
    )


def clear_window(apps, schema_editor):
    HealthCheckCampaign = apps.get_model('surveys', 'HealthCheckCampaign')
    HealthCheckCampaign.objects.filter(code='ksk-2026-10').update(
        opens_at=None,
        closes_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0008_healthcheck_window'),
    ]

    operations = [
        migrations.RunPython(set_window, clear_window),
    ]
