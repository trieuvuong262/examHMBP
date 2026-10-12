from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0006_cancel_open_qa_tasks'),
    ]

    operations = [
        migrations.RemoveField(model_name='productdevelopment', name='product_type'),
    ]
