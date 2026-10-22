from datetime import time

from django.db import migrations


def create_office_shift(apps, schema_editor):
    Shift = apps.get_model('cham_cong', 'Shift')
    if Shift.objects.filter(name='Hành chính').exists():
        return
    Shift.objects.create(
        name='Hành chính',
        kind='office',
        start_time=time(8, 0),
        end_time=time(17, 0),
        break_start=time(12, 0),
        break_end=time(13, 0),
        crosses_midnight=False,
        late_grace_minutes=5,
        early_grace_minutes=5,
        saturday_start=time(8, 0),
        saturday_end=time(12, 0),
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('cham_cong', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_office_shift, migrations.RunPython.noop),
    ]
