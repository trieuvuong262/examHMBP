import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nas_storage', '0002_rename_nas_storage_created_8a0f0d_idx_nas_storage_created_75c74a_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='NasUserFolderAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=120, verbose_name='Tên hiển thị')),
                ('rel_path', models.CharField(help_text='VD: HCNS/Annt hoặc IT/_CHUNG (tương đối gốc mount NAS)', max_length=500, verbose_name='Đường dẫn NAS')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='Mô tả')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nas_folder_accesses', to=settings.AUTH_USER_MODEL, verbose_name='Tài khoản')),
            ],
            options={
                'verbose_name': 'Thư mục NAS (theo user)',
                'verbose_name_plural': 'Thư mục NAS (theo user)',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='nasuserfolderaccess',
            constraint=models.UniqueConstraint(fields=('user', 'rel_path'), name='nas_storage_user_folder_rel_path_uniq'),
        ),
    ]
