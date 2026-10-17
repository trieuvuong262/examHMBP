import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('utilities', '0015_gomoku_undo_offer'),
    ]

    operations = [
        migrations.CreateModel(
            name='GomokuMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.CharField(max_length=300, verbose_name='Nội dung')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Gửi lúc')),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='utilities.gomokuroom', verbose_name='Phòng')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='Người gửi')),
            ],
            options={
                'verbose_name': 'Tin nhắn Caro',
                'verbose_name_plural': 'Tin nhắn Caro',
                'ordering': ['id'],
                'indexes': [models.Index(fields=['room', 'id'], name='util_gomoku_msg_room_idx')],
            },
        ),
    ]
