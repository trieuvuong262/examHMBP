"""Map dữ liệu kế hoạch cũ sang phương án MTO/MPS + đổ qty_gross cho dòng cũ.

  source = sales_order  → MTO (đã lập từ đơn KiotViet)
  source = forecast     → MPS (nhập tay theo kỳ = lịch trình chủ)
"""

from django.db import migrations


def forward(apps, schema_editor):
    SxOverallPlan = apps.get_model('san_xuat', 'SxOverallPlan')
    SxOverallPlanLine = apps.get_model('san_xuat', 'SxOverallPlanLine')

    SxOverallPlan.objects.filter(source='sales_order').update(plan_method='mto')
    SxOverallPlan.objects.exclude(source='sales_order').update(plan_method='mps')

    # Kế hoạch cũ chưa có netting — giữ nguyên số đã nhập tay
    SxOverallPlan.objects.all().update(apply_netting=False)

    # qty_gross = qty_required (hoặc qty_planned) để không mất dữ liệu đối chiếu
    for line in SxOverallPlanLine.objects.all().iterator(chunk_size=500):
        gross = line.qty_required or line.qty_planned or 0
        if line.qty_gross != gross:
            line.qty_gross = gross
            line.save(update_fields=['qty_gross'])


def backward(apps, schema_editor):
    # Không cần hoàn nguyên: các trường sẽ bị xóa khi rollback 0045
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0045_p2_plan_methods'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
