from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0005_user_guide'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='must_change_password',
            field=models.BooleanField(
                default=False,
                verbose_name='Bắt buộc đổi mật khẩu lần đầu',
            ),
        ),
    ]
