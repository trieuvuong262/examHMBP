# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def _backfill_team_slug(apps, schema_editor):
    SxQcRequest = apps.get_model('san_xuat', 'SxQcRequest')
    from san_xuat.services.progress_template import (
        team_slug_for_process_label,
        team_slug_for_work_center_code,
    )

    for req in SxQcRequest.objects.all().iterator():
        slug = ''
        stage = (req.stage_name or '').strip()
        if stage:
            slug = team_slug_for_process_label(stage) or team_slug_for_work_center_code(stage) or ''
        if slug and req.team_slug != slug:
            req.team_slug = slug
            req.save(update_fields=['team_slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0095_fg_partial_and_stock_receipt_link'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxqcrequest',
            name='team_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='cat / inep / theu / may / ht / gh — khớp Ob khi lên đơn.',
                max_length=20,
                verbose_name='Tổ QC',
            ),
        ),
        migrations.AddField(
            model_name='sxqcrequest',
            name='work_center',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='qc_requests',
                to='san_xuat.sxworkcenter',
                verbose_name='Tổ / bộ phận',
            ),
        ),
        migrations.RunPython(_backfill_team_slug, migrations.RunPython.noop),
    ]
