# Generated manually for Profile.phone (Zalo OTP P0)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0072_seed_san_xuat_ops_menus'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='phone',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Lưu dạng 84xxxxxxxxx — dùng gửi OTP Zalo.',
                max_length=20,
                verbose_name='Số điện thoại',
            ),
        ),
        migrations.AddConstraint(
            model_name='profile',
            constraint=models.UniqueConstraint(
                condition=~models.Q(phone=''),
                fields=('phone',),
                name='uniq_profile_phone_nonempty',
            ),
        ),
    ]
