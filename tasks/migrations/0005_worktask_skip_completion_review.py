from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_cross_department_projects'),
    ]

    operations = [
        migrations.AddField(
            model_name='worktask',
            name='skip_completion_review',
            field=models.BooleanField(
                default=False,
                help_text='Nhân viên nộp xong được chốt hoàn thành luôn, không qua bước chờ duyệt.',
                verbose_name='Không cần duyệt hoàn thành',
            ),
        ),
    ]
