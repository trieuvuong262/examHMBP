from django.db import migrations, models


def copy_creation_notes(apps, schema_editor):
    """Ghi chú lúc tạo hồ sơ trước đây chỉ nằm trong lịch sử — đưa vào trường hồ sơ."""
    Candidate = apps.get_model('recruitment', 'Candidate')
    Event = apps.get_model('recruitment', 'CandidateEvent')
    seen = set()
    notes = (
        Event.objects.filter(kind='note')
        .exclude(message__startswith='Đạt nhưng vị trí')
        .order_by('candidate_id', 'created_at', 'id')
        .values_list('candidate_id', 'message')
    )
    for candidate_id, message in notes.iterator():
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        text = (message or '').strip()
        if text:
            Candidate.objects.filter(pk=candidate_id, note='').update(note=text)


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0024_job_interviewers_skip_cv_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='note',
            field=models.TextField(blank=True, verbose_name='Ghi chú'),
        ),
        migrations.RunPython(copy_creation_notes, migrations.RunPython.noop),
    ]
