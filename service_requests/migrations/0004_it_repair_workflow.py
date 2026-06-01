from django.db import migrations, models


def seed_it_repair_type(apps, schema_editor):
    RequestType = apps.get_model('service_requests', 'RequestType')
    RequestType.objects.get_or_create(
        code='it_repair',
        defaults={
            'name': 'Sửa chữa IT',
            'description': (
                'Báo hỏng máy tính, mạng, phần mềm — IT xử lý trực tiếp, không duyệt TL/BP.'
            ),
            'is_active': True,
            'sort_order': 2,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('service_requests', '0003_procurement_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerequest',
            name='blocks_work',
            field=models.BooleanField(default=False, verbose_name='Đang chặn công việc'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='equipment_label',
            field=models.CharField(blank=True, max_length=200, verbose_name='Thiết bị (tên/mã)'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='equipment_serial',
            field=models.CharField(blank=True, max_length=100, verbose_name='Serial'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='expected_return_date',
            field=models.DateField(blank=True, null=True, verbose_name='Dự kiến hoàn thành'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='incident_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('hw', 'Phần cứng'),
                    ('sw', 'Phần mềm'),
                    ('network', 'Mạng / Internet'),
                    ('account', 'Tài khoản / quyền truy cập'),
                    ('other', 'Khác'),
                ],
                max_length=20,
                verbose_name='Loại sự cố',
            ),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='location_text',
            field=models.CharField(blank=True, max_length=200, verbose_name='Vị trí'),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='priority',
            field=models.CharField(
                blank=True,
                choices=[
                    ('low', 'Thấp'),
                    ('normal', 'Bình thường'),
                    ('high', 'Cao'),
                    ('urgent', 'Khẩn — chặn công việc'),
                ],
                max_length=20,
                verbose_name='Mức độ ưu tiên',
            ),
        ),
        migrations.AddField(
            model_name='servicerequest',
            name='repair_cost',
            field=models.DecimalField(
                blank=True,
                decimal_places=0,
                max_digits=14,
                null=True,
                verbose_name='Chi phí sửa (VNĐ)',
            ),
        ),
        migrations.RunPython(seed_it_repair_type, migrations.RunPython.noop),
    ]
