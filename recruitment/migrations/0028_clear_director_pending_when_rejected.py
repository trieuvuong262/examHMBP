"""Hồ sơ đã loại hoặc phỏng vấn Không đạt thì không còn «Chờ giám đốc duyệt»."""

from django.db import migrations


def forward(apps, schema_editor):
    Interview = apps.get_model('recruitment', 'Interview')
    Interview.objects.filter(final_result='pending', result='fail').update(final_result='')
    Interview.objects.filter(final_result='pending', candidate__status='rejected').update(final_result='')


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0027_job_skip_director_approval'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
