from django.db import migrations


def forwards(apps, schema_editor):
    Task = apps.get_model('thiet_ke_sp', 'Task')
    Task.objects.filter(role='qa_user', state='open').update(state='cancelled')


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0005_product_type_fk'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
