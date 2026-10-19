from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utilities', '0017_gomoku_public_room'),
    ]

    operations = [
        migrations.AddField(
            model_name='gomokuroom',
            name='turn_hold',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Giây còn lại khi tạm dừng'),
        ),
    ]
