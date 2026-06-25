from django.db import migrations


def remove_odoo_training(apps, schema_editor):
    Document = apps.get_model('documents', 'Document')
    DocumentCategory = apps.get_model('documents', 'DocumentCategory')
    Document.objects.filter(category__slug='huong-dan-odoo').delete()
    DocumentCategory.objects.filter(slug='huong-dan-odoo').delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0010_odoo_training_local_links'),
    ]

    operations = [
        migrations.RunPython(remove_odoo_training, noop),
    ]
