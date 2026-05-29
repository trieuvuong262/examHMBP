from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '0005_qa_flash_models_only'),
    ]

    operations = [
        migrations.CreateModel(
            name='LibraryQAChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'Người dùng'), ('model', 'Trợ lý AI')], max_length=10, verbose_name='Vai trò')),
                ('text', models.TextField(verbose_name='Nội dung')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_qa_messages', to=settings.AUTH_USER_MODEL, verbose_name='Người dùng')),
            ],
            options={
                'verbose_name': 'Tin nhắn Hỏi đáp AI',
                'verbose_name_plural': 'Tin nhắn Hỏi đáp AI',
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['user', 'created_at'], name='documents_l_user_id_6a8f2d_idx')],
            },
        ),
    ]
