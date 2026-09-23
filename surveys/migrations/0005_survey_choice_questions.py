import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0004_surveyview'),
    ]

    operations = [
        migrations.AlterField(
            model_name='survey',
            name='question',
            field=models.TextField(
                blank=True,
                help_text='Tóm tắt các câu hỏi. Khảo sát cũ dùng ô này làm câu hỏi tự luận.',
                verbose_name='Nội dung câu hỏi',
            ),
        ),
        migrations.CreateModel(
            name='SurveyQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(verbose_name='Nội dung câu hỏi')),
                ('is_required', models.BooleanField(default=True, verbose_name='Bắt buộc')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('survey', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='surveys.survey', verbose_name='Khảo sát')),
            ],
            options={
                'verbose_name': 'Câu hỏi khảo sát',
                'verbose_name_plural': 'Câu hỏi khảo sát',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='SurveyOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=500, verbose_name='Đáp án')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Thứ tự')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='surveys.surveyquestion', verbose_name='Câu hỏi')),
            ],
            options={
                'verbose_name': 'Đáp án',
                'verbose_name_plural': 'Đáp án',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='SurveyAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('option', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='selections', to='surveys.surveyoption', verbose_name='Đáp án đã chọn')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='surveys.surveyquestion', verbose_name='Câu hỏi')),
                ('response', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='surveys.surveyresponse', verbose_name='Phản hồi')),
            ],
            options={
                'verbose_name': 'Lựa chọn đáp án',
                'verbose_name_plural': 'Lựa chọn đáp án',
                'ordering': ['question__sort_order', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='surveyanswer',
            constraint=models.UniqueConstraint(fields=('response', 'question'), name='surveys_unique_answer_per_question'),
        ),
    ]
