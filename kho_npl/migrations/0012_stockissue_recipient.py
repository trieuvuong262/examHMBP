"""Người nhận phiếu xuất — chọn từ danh sách nhân viên."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_issue_recipient(apps, schema_editor):
    StockIssue = apps.get_model('kho_npl', 'StockIssue')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    for issue in StockIssue.objects.exclude(recipient_name='').iterator():
        name = (issue.recipient_name or '').strip()
        if not name:
            continue
        user = User.objects.filter(username__iexact=name).first()
        if not user:
            user = User.objects.filter(profile__full_name__iexact=name).first()
        if not user:
            user = User.objects.filter(profile__employee_code__iexact=name).first()
        if user:
            issue.recipient_id = user.pk
            issue.save(update_fields=['recipient_id'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kho_npl', '0011_material_category_parent_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockissue',
            name='recipient',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='npl_issues_received',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người nhận',
            ),
        ),
        migrations.RunPython(backfill_issue_recipient, migrations.RunPython.noop),
    ]
