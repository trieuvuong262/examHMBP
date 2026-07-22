import san_xuat.design_nas_storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0024_tech_doc_description'),
    ]

    operations = [
        migrations.AlterField(
            model_name='techdocdesignfile',
            name='file',
            field=models.FileField(
                max_length=500,
                storage=san_xuat.design_nas_storage.DesignDocNasStorage(),
                upload_to=san_xuat.design_nas_storage.design_file_upload_to,
                verbose_name='Tệp',
            ),
        ),
    ]
