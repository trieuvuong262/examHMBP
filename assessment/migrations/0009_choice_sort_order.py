import re

from django.db import migrations, models


def populate_choice_sort_order(apps, schema_editor):
    Choice = apps.get_model('assessment', 'Choice')
    question_ids = (
        Choice.objects.order_by()
        .values_list('question_id', flat=True)
        .distinct()
    )
    for question_id in question_ids:
        choices = list(Choice.objects.filter(question_id=question_id))

        def sort_key(choice):
            text = (choice.text or '').strip()
            match = re.match(r'^([A-Z])\.\s*', text)
            if match:
                return ord(match.group(1))
            return choice.id

        choices.sort(key=sort_key)
        for idx, choice in enumerate(choices, start=1):
            choice.sort_order = idx
            choice.save(update_fields=['sort_order'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0008_examquestion_sort_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='choice',
            name='sort_order',
            field=models.PositiveIntegerField(default=1, verbose_name='STT'),
        ),
        migrations.RunPython(populate_choice_sort_order, noop_reverse),
        migrations.AlterModelOptions(
            name='choice',
            options={
                'ordering': ['sort_order', 'id'],
                'verbose_name': 'Đáp án',
                'verbose_name_plural': 'Đáp án',
            },
        ),
    ]
