from django.db import migrations


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0008_ensure_library_qa_index'),
    ]

    operations = [
        migrations.RunPython(noop, noop),
    ]
