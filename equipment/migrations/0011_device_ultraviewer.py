from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipment', '0010_agentinstalltoken_machine_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='ultraviewer_id',
            field=models.CharField(blank=True, max_length=32, verbose_name='UltraViewer ID'),
        ),
        migrations.AddField(
            model_name='device',
            name='ultraviewer_password',
            field=models.CharField(blank=True, max_length=128, verbose_name='UltraViewer mật khẩu'),
        ),
    ]
