from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0031_candidate_joined_then_left'),
    ]

    operations = [
        migrations.AlterField(
            model_name='candidate',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'Mới'),
                    ('reviewing', 'Chờ quản lý đánh giá'),
                    ('interviewing', 'Phỏng vấn'),
                    ('offered', 'Trúng tuyển'),
                    ('hired', 'Đã nhận việc'),
                    ('joined_then_left', 'Nhận việc nhưng nghỉ việc'),
                    ('not_onboarded', 'Không nhận việc'),
                    ('rejected', 'Loại'),
                ],
                db_index=True,
                default='new',
                max_length=20,
                verbose_name='Trạng thái',
            ),
        ),
    ]
