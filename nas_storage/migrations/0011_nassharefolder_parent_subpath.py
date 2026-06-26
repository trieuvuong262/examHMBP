from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nas_storage', '0010_alter_nasfolderpermission_options_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='nassharefolder',
            options={
                'ordering': ['sort_order', 'share_name', 'sub_path'],
                'verbose_name': 'Thư mục NAS',
                'verbose_name_plural': 'Thư mục NAS',
            },
        ),
        migrations.AddField(
            model_name='nassharefolder',
            name='inherits_permissions',
            field=models.BooleanField(default=True, verbose_name='Kế thừa phân quyền từ cha'),
        ),
        migrations.AddField(
            model_name='nassharefolder',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='children',
                to='nas_storage.nassharefolder',
                verbose_name='Thư mục cha',
            ),
        ),
        migrations.AddField(
            model_name='nassharefolder',
            name='sub_path',
            field=models.CharField(
                blank=True,
                help_text='VD: KD-MKT/_CHUNG — chỉ với thư mục con.',
                max_length=500,
                verbose_name='Đường dẫn trong share',
            ),
        ),
        migrations.AlterField(
            model_name='nassharefolder',
            name='share_name',
            field=models.CharField(
                help_text='VD: 07_SAN_XUAT — chỉ nhập với thư mục gốc (share).',
                max_length=120,
                verbose_name='Tên share NAS',
            ),
        ),
        migrations.AddConstraint(
            model_name='nassharefolder',
            constraint=models.UniqueConstraint(
                condition=models.Q(('parent__isnull', True)),
                fields=('share_name',),
                name='nas_storage_share_root_name_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='nassharefolder',
            constraint=models.UniqueConstraint(
                condition=models.Q(('parent__isnull', False)),
                fields=('parent', 'sub_path'),
                name='nas_storage_share_child_path_uniq',
            ),
        ),
    ]
