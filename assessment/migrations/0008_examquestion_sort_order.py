from django.db import migrations, models
import django.db.models.deletion


def populate_exam_questions(apps, schema_editor):
    Exam = apps.get_model('assessment', 'Exam')
    ExamQuestion = apps.get_model('assessment', 'ExamQuestion')
    for exam in Exam.objects.all().iterator():
        for idx, question in enumerate(exam.questions.order_by('id'), start=1):
            ExamQuestion.objects.create(
                exam_id=exam.pk,
                question_id=question.pk,
                sort_order=idx,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0007_delete_profile'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=1, verbose_name='STT trong đề')),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_questions', to='assessment.exam')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_links', to='assessment.question')),
            ],
            options={
                'verbose_name': 'Câu hỏi trong đề',
                'verbose_name_plural': 'Câu hỏi trong đề',
                'ordering': ['sort_order', 'id'],
                'unique_together': {('exam', 'question')},
            },
        ),
        migrations.RunPython(populate_exam_questions, noop_reverse),
        migrations.RemoveField(
            model_name='exam',
            name='questions',
        ),
        migrations.AddField(
            model_name='exam',
            name='questions',
            field=models.ManyToManyField(related_name='exams', through='assessment.ExamQuestion', to='assessment.question', verbose_name='Câu hỏi trong đề'),
        ),
    ]
