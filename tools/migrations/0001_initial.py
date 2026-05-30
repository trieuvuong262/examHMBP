from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=120, verbose_name='Tiêu đề')),
                ('content', models.TextField(blank=True, verbose_name='Nội dung')),
                ('color', models.CharField(choices=[('yellow', 'Vàng'), ('blue', 'Xanh dương'), ('green', 'Xanh lá'), ('pink', 'Hồng'), ('gray', 'Xám')], default='yellow', max_length=20, verbose_name='Màu')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Cập nhật')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Tạo lúc')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tool_notes', to=settings.AUTH_USER_MODEL, verbose_name='Người dùng')),
            ],
            options={
                'verbose_name': 'Ghi chú',
                'verbose_name_plural': 'Ghi chú',
                'ordering': ['sort_order', '-updated_at'],
            },
        ),
    ]
