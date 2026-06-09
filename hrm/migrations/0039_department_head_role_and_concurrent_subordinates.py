from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hrm', '0038_profile_concurrent_position'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[
                    ('EMPLOYEE', 'Nhân viên'),
                    ('TEAM_LEADER', 'Tổ trưởng'),
                    ('DIVISION_HEAD', 'Trưởng bộ phận'),
                    ('DEPARTMENT_HEAD', 'Trưởng phòng'),
                    ('DIRECTOR', 'Giám đốc'),
                ],
                default='EMPLOYEE',
                max_length=20,
                verbose_name='Vai trò hệ thống',
            ),
        ),
        migrations.AlterField(
            model_name='profileconcurrentposition',
            name='role',
            field=models.CharField(
                choices=[
                    ('EMPLOYEE', 'Nhân viên'),
                    ('TEAM_LEADER', 'Tổ trưởng'),
                    ('DIVISION_HEAD', 'Trưởng bộ phận'),
                    ('DEPARTMENT_HEAD', 'Trưởng phòng'),
                    ('DIRECTOR', 'Giám đốc'),
                ],
                default='EMPLOYEE',
                max_length=20,
                verbose_name='Vai trò tại vị trí kiêm nhiệm',
            ),
        ),
        migrations.AddField(
            model_name='profileconcurrentposition',
            name='subordinates',
            field=models.ManyToManyField(
                blank=True,
                related_name='concurrent_manager_slots',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Nhân viên cấp dưới tại slot kiêm nhiệm',
            ),
        ),
    ]
