# Generated manually for portal browse-all NAS groups

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('nas_storage', '0006_nasuserfolderacl'),
    ]

    operations = [
        migrations.AddField(
            model_name='nasaccessgroup',
            name='portal_browse_all',
            field=models.BooleanField(
                default=False,
                help_text='Thành viên nhóm xem được mọi share trên menu Duyệt thư mục.',
                verbose_name='Duyệt tất cả share (Portal)',
            ),
        ),
        migrations.AddField(
            model_name='nasaccessgroup',
            name='portal_members',
            field=models.ManyToManyField(
                blank=True,
                help_text='User được tính vào nhóm dù phòng ban khác (vd. ductn vào Ban Giám đốc).',
                related_name='nas_portal_access_groups',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Thành viên bổ sung (Portal)',
            ),
        ),
    ]
