# Generated manually

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nas_storage', '0007_nasaccessgroup_portal_browse'),
    ]

    operations = [
        migrations.AddField(
            model_name='nasaccessgroup',
            name='portal_excluded_members',
            field=models.ManyToManyField(
                blank=True,
                help_text='User thuộc phòng ban nhóm nhưng không được tính vào nhóm (không xem tất cả share).',
                related_name='nas_portal_excluded_groups',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Loại trừ khỏi nhóm (Portal)',
            ),
        ),
    ]
