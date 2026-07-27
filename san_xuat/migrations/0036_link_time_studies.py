from django.db import migrations


def link_time_studies(apps, schema_editor):
    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event
    from san_xuat.services.ie_ops import link_time_studies_to_operations

    stats = link_time_studies_to_operations(only_unlinked=True)
    log_ie_event(
        action=SxIeAuditLog.ACTION_LINK,
        summary=(
            f"Migration 0036: gắn FK time study → operation "
            f"({stats['linked']} linked, {stats['skipped']} skipped)"
        ),
        object_type='SxTimeStudy',
        object_repr='migration_link',
        changes=stats,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0035_ie_audit_and_link'),
    ]

    operations = [
        migrations.RunPython(link_time_studies, noop_reverse),
    ]
