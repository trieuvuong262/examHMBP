from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nas_storage', '0008_nasaccessgroup_portal_excluded'),
    ]

    operations = [
        migrations.AddField(
            model_name='nasfolderpermission',
            name='user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='nas_folder_permissions',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Nhân viên',
            ),
        ),
        migrations.AlterField(
            model_name='nasfolderpermission',
            name='group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='folder_permissions',
                to='nas_storage.nasaccessgroup',
                verbose_name='Nhóm',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='nasfolderpermission',
            name='nas_storage_folder_group_perm_uniq',
        ),
        migrations.AddConstraint(
            model_name='nasfolderpermission',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('group__isnull', False),
                    ('user__isnull', True),
                ) | models.Q(
                    ('group__isnull', True),
                    ('user__isnull', False),
                ),
                name='nas_folder_perm_group_xor_user',
            ),
        ),
        migrations.AddConstraint(
            model_name='nasfolderpermission',
            constraint=models.UniqueConstraint(
                condition=models.Q(('group__isnull', False)),
                fields=('folder', 'group'),
                name='nas_storage_folder_group_perm_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='nasfolderpermission',
            constraint=models.UniqueConstraint(
                condition=models.Q(('user__isnull', False)),
                fields=('folder', 'user'),
                name='nas_storage_folder_user_perm_uniq',
            ),
        ),
    ]
