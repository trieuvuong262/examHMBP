"""Chuyển kho nhập thành phẩm từ chữ tự do sang FK.

Giá trị cũ có dạng ``kv:<id chi nhánh KiotViet>`` (vd. ``kv:4`` = "Xưởng sản
xuất"). Vì thành phẩm chỉ nhập vào kho thành phẩm ở xưởng, mọi phiếu cũ đều
ánh xạ về đúng kho đó — không cần suy luận từ con số id KiotViet, con số ấy sẽ
hết nghĩa khi bỏ KiotViet.

Mã và tên kho để nguyên trong file này thay vì import từ ``choices`` vì
migration phải chạy đúng với dữ liệu tại thời điểm nó được viết.
"""

from django.db import migrations

FG_WAREHOUSE_CODE = 'XUONG-TP'
FG_WAREHOUSE_NAME = 'Kho thành phẩm — Xưởng sản xuất'
OWNER_PORTAL = 'portal'


def backfill(apps, schema_editor):
    Warehouse = apps.get_model('kho_san_pham', 'Warehouse')
    SxFgReceiptRequest = apps.get_model('san_xuat', 'SxFgReceiptRequest')

    pending = SxFgReceiptRequest.objects.filter(warehouse__isnull=True)
    if not pending.exists():
        return

    warehouse, _ = Warehouse.objects.get_or_create(
        code=FG_WAREHOUSE_CODE,
        defaults={'name': FG_WAREHOUSE_NAME, 'owner_system': OWNER_PORTAL},
    )
    pending.update(warehouse=warehouse)


def unbackfill(apps, schema_editor):
    # Chỉ bỏ liên kết. Không xóa Warehouse: có thể đã phát sinh tồn trỏ vào nó.
    SxFgReceiptRequest = apps.get_model('san_xuat', 'SxFgReceiptRequest')
    SxFgReceiptRequest.objects.update(warehouse=None)


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0085_sxfgreceiptrequest_warehouse_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
