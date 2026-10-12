from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('recruitment', '0023_job_position_freetext'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobposting',
            name='interviewers',
            field=models.ManyToManyField(
                blank=True, related_name='job_postings_interviewing', to=settings.AUTH_USER_MODEL,
                verbose_name='Người phỏng vấn',
            ),
        ),
        migrations.AddField(
            model_name='jobposting',
            name='skip_cv_review',
            field=models.BooleanField(default=False, verbose_name='Bỏ qua duyệt CV'),
        ),
    ]
