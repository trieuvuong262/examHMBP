from django.db import migrations

# Import Excel (và đoạn sync mẫu cũ) từng gán status='approved' trực tiếp, bỏ qua
# approve_operation() nên không có approved_at/approved_user. Kết quả: thư viện ghi
# "Đã duyệt" trong khi không ai bấm Duyệt. Đưa các bản ghi đó về "Thử nghiệm" để IE
# duyệt lại đúng quy trình. Công đoạn có approved_at (duyệt thật) không bị chạm.


def forwards(apps, schema_editor):
    SxOperation = apps.get_model('san_xuat', 'SxOperation')

    SxOperation.objects.filter(
        status='approved',
        approved_at__isnull=True,
    ).update(
        status='trial',
        approved_by='',
        approved_user=None,
    )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0080_drop_legacy_process_stages'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
