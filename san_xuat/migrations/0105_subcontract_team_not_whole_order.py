from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0104_alter_sxsubcontractorder_team_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sxsubcontractorder',
            name='team_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Bắt buộc theo bộ phận. Phiếu cũ để trống không còn được coi là cả lệnh.',
                max_length=20,
                verbose_name='Tổ Ob thuê ngoài',
            ),
        ),
    ]
