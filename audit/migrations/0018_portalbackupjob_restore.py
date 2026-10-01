from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0017_responsetimedaily_dbquerysnapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='portalbackupjob',
            name='kind',
            field=models.CharField(
                choices=[('backup', 'Backup'), ('restore', 'Khôi phục')],
                db_index=True,
                default='backup',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='portalbackupjob',
            name='scope',
            field=models.CharField(
                blank=True,
                choices=[('code', 'Mã nguồn'), ('data', 'Dữ liệu'), ('all', 'Toàn bộ')],
                default='',
                max_length=16,
            ),
        ),
    ]
