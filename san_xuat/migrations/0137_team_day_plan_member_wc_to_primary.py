# Generated manually

from django.db import migrations


def _reset_member_wc(apps, schema_editor):
    """Ngày KHSX gắn tổ thành viên (không phải tổ chính) của slug gộp → về tổ chính (NULL)."""
    from san_xuat.hub_models import SxOrderTeamDayPlan
    from san_xuat.models import SxSalesOrder
    from san_xuat.services.plan_board import _team_loads_from_order

    order_ids = (
        SxOrderTeamDayPlan.objects.exclude(work_center_id__isnull=True)
        .values_list('sales_order_id', flat=True)
        .distinct()
    )
    for order in SxSalesOrder.objects.filter(pk__in=list(order_ids)):
        for row in _team_loads_from_order(order):
            primary = int(row.get('work_center_id') or 0)
            others = {int(x) for x in row.get('member_wc_ids') or [] if int(x) != primary}
            if not primary or not others:
                continue
            day_qs = SxOrderTeamDayPlan.objects.filter(sales_order=order, team_slug=row['slug'])
            if day_qs.filter(work_center_id=primary).exists():
                continue
            day_qs.filter(work_center_id__in=others).update(work_center=None)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0136_team_progress_log_kind'),
    ]

    operations = [
        migrations.RunPython(_reset_member_wc, noop),
    ]
