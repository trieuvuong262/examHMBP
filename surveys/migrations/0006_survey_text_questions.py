import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0005_survey_choice_questions'),
    ]

    operations = [
        migrations.AddField(
            model_name='surveyquestion',
            name='q_type',
            field=models.CharField(
                choices=[('choice', 'Chọn 1 đáp án'), ('text', 'Nhập text')],
                default='choice',
                max_length=20,
                verbose_name='Loại câu hỏi',
            ),
        ),
        migrations.AddField(
            model_name='surveyanswer',
            name='text_value',
            field=models.TextField(blank=True, verbose_name='Nội dung nhập'),
        ),
        migrations.AlterField(
            model_name='surveyanswer',
            name='option',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='selections',
                to='surveys.surveyoption',
                verbose_name='Đáp án đã chọn',
            ),
        ),
    ]
