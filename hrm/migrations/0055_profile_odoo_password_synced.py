from django.db import migrations, models


def mark_existing_odoo_users_unsynced(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    Profile.objects.filter(odoo_user_id__isnull=False).update(odoo_password_synced=False)


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0054_promote_odoo_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='odoo_password_synced',
            field=models.BooleanField(
                default=False,
                help_text='True sau khi đổi/reset mật khẩu Portal và đồng bộ sang Odoo.',
                verbose_name='Mật khẩu Odoo đã khớp Portal',
            ),
        ),
        migrations.RunPython(mark_existing_odoo_users_unsynced, migrations.RunPython.noop),
    ]
