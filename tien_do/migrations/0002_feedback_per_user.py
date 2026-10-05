import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def move_feedback_to_entries(apps, schema_editor):
    """Chuyển Feedback / Ghi chú cũ (một ô chung) thành bản ghi TienDoFeedback, người gửi để trống."""
    TienDoItem = apps.get_model('tien_do', 'TienDoItem')
    TienDoFeedback = apps.get_model('tien_do', 'TienDoFeedback')
    entries = []
    for item in TienDoItem.objects.all().only('id', 'feedback', 'note'):
        feedback = (item.feedback or '').strip()
        note = (item.note or '').strip()
        if feedback or note:
            entries.append(TienDoFeedback(item_id=item.id, feedback=feedback, note=note))
    if entries:
        TienDoFeedback.objects.bulk_create(entries)


class Migration(migrations.Migration):

    dependencies = [
        ('tien_do', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TienDoFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('feedback', models.TextField(blank=True, verbose_name='Feedback')),
                ('note', models.TextField(blank=True, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tien_do_feedbacks', to=settings.AUTH_USER_MODEL, verbose_name='Người gửi')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedbacks', to='tien_do.tiendoitem', verbose_name='Dòng tiến độ')),
            ],
            options={
                'verbose_name': 'Feedback tiến độ',
                'verbose_name_plural': 'Feedback tiến độ',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.RunPython(move_feedback_to_entries, migrations.RunPython.noop),
        migrations.RemoveField(model_name='tiendoitem', name='feedback'),
        migrations.RemoveField(model_name='tiendoitem', name='note'),
        migrations.RemoveField(model_name='tiendoitem', name='is_tested'),
    ]
