from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0163_retire_gh_stage_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='sxteamprogresslog',
            name='revised_qty',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='SL sau khi sửa',
            ),
        ),
        migrations.AddField(
            model_name='sxteamprogresslog',
            name='revised_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Lúc sửa'),
        ),
        migrations.AddField(
            model_name='sxteamprogresslog',
            name='revised_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sx_team_progress_log_revisions',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người sửa',
            ),
        ),
    ]
