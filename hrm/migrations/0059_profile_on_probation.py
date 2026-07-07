from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import migrations, models


def clear_expired_probation(apps, schema_editor):
    Profile = apps.get_model('hrm', 'Profile')
    today = date.today()
    to_clear = []
    for pk, join_date in Profile.objects.filter(
        on_probation=True,
        join_date__isnull=False,
    ).values_list('pk', 'join_date'):
        if today >= join_date + relativedelta(months=2):
            to_clear.append(pk)
    if to_clear:
        Profile.objects.filter(pk__in=to_clear).update(on_probation=False)


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0058_nas_download_to_documents'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='on_probation',
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text='Mặc định bật khi tạo mới; tự tắt sau 2 tháng kể từ ngày vào.',
                verbose_name='Thử việc',
            ),
        ),
        migrations.RunPython(clear_expired_probation, migrations.RunPython.noop),
    ]
