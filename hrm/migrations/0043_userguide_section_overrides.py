from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0042_alter_permissiongroup_module_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='userguide',
            name='section_overrides',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Nội dung tùy chỉnh theo mục: {section_id: {title?, body}}',
                verbose_name='Ghi đè theo mục',
            ),
        ),
    ]
