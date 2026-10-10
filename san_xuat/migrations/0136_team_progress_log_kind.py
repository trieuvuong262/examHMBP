from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0135_team_progress_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxteamprogresslog',
            name='kind',
            field=models.CharField(choices=[('edit', 'Nhập tay'), ('complete', 'Hoàn thành')], default='edit', max_length=10, verbose_name='Loại'),
        ),
    ]
