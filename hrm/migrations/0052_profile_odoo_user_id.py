from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0051_sync_nas_monitor_menu_perm'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='odoo_user_id',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Đồng bộ từ Portal khi có quyền menu Odoo.',
                null=True,
                verbose_name='Odoo res.users ID',
            ),
        ),
    ]
