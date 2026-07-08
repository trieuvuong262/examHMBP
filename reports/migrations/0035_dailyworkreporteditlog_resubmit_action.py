from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0034_rename_reports_dai_report__a8f2c1_idx_reports_dai_report__a79895_idx'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dailyworkreporteditlog',
            name='action',
            field=models.CharField(
                choices=[
                    ('update', 'Chỉnh sửa'),
                    ('submit', 'Gửi báo cáo'),
                    ('resubmit', 'Cập nhật báo cáo'),
                ],
                default='update',
                max_length=20,
                verbose_name='Thao tác',
            ),
        ),
    ]
