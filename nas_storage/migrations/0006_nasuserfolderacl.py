import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nas_storage', '0005_nas_folder_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='NasUserFolderAcl',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sub_path', models.CharField(help_text='VD: lvanhthu (→ /volume1/05_MARKETING/lvanhthu)', max_length=500, verbose_name='Thư mục con trong share')),
                ('access_level', models.CharField(choices=[('RW', 'Đọc + Ghi'), ('RO', 'Chỉ đọc')], default='RW', max_length=4, verbose_name='Mức quyền')),
                ('label', models.CharField(blank=True, max_length=120, verbose_name='Ghi chú')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang dùng')),
                ('last_applied_at', models.DateTimeField(blank=True, null=True, verbose_name='Áp dụng NAS lần cuối')),
                ('last_apply_status', models.CharField(blank=True, max_length=500, verbose_name='Trạng thái áp dụng')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('folder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_folder_acls', to='nas_storage.nassharefolder', verbose_name='Share NAS')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nas_folder_acls', to=settings.AUTH_USER_MODEL, verbose_name='Tài khoản Portal')),
            ],
            options={
                'verbose_name': 'ACL thư mục riêng (user)',
                'verbose_name_plural': 'ACL thư mục riêng (user)',
                'ordering': ['user__username', 'folder__sort_order', 'sub_path'],
            },
        ),
        migrations.AddConstraint(
            model_name='nasuserfolderacl',
            constraint=models.UniqueConstraint(fields=('user', 'folder', 'sub_path'), name='nas_storage_user_folder_acl_uniq'),
        ),
    ]
