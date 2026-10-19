from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0016_gomoku_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='gomokuroom',
            name='is_public',
            field=models.BooleanField(default=False, verbose_name='Phòng công khai'),
        ),
    ]
