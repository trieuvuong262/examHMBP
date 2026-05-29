from django.db import migrations


AXES_TABLES = (
    'axes_accessattemptexpiration',
    'axes_accessfailurelog',
    'axes_accesslog',
    'axes_accessattempt',
)


def drop_axes_tables(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    tables = ', '.join(f'"{name}"' for name in AXES_TABLES)
    schema_editor.execute(f'DROP TABLE IF EXISTS {tables} CASCADE;')
    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'axes';")


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0003_rename_audit_useract_user_id_created_idx_audit_usera_user_id_1d091e_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_axes_tables, migrations.RunPython.noop),
    ]
