from django.db import migrations
from django.utils import timezone


def cancel_open_receipt_tasks(apps, schema_editor):
    """Việc xác nhận nhận bàn giao của 4 bộ phận không còn trong quy trình."""
    Task = apps.get_model('thiet_ke_sp', 'Task')
    Task.objects.filter(receipt__isnull=False, state='open').update(
        state='cancelled',
        completed_at=timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0011_materialline_kho_npl'),
    ]

    operations = [
        migrations.RunPython(cancel_open_receipt_tasks, migrations.RunPython.noop),
    ]
