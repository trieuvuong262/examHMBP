# Generated manually

from django.db import migrations, models


def _backfill_team_slug(apps, schema_editor):
    SxSubcontractOrder = apps.get_model('san_xuat', 'SxSubcontractOrder')
    from san_xuat.services.progress_template import (
        team_slug_for_process_label,
        team_slug_for_work_center_code,
    )

    for row in SxSubcontractOrder.objects.all().iterator():
        if (row.team_slug or '').strip():
            continue
        raw = (row.process_name or '').strip()
        slug = team_slug_for_process_label(raw) or team_slug_for_work_center_code(raw) or ''
        if slug:
            row.team_slug = slug
            row.save(update_fields=['team_slug'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0099_seed_team_qc_criteria'),
    ]

    operations = [
        migrations.AddField(
            model_name='sxsubcontractorder',
            name='team_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Tổ trên Ob của lệnh được thuê ngoài — không mặc định thêu.',
                max_length=20,
                verbose_name='Tổ Ob thuê ngoài',
            ),
        ),
        migrations.RunPython(_backfill_team_slug, noop),
    ]
