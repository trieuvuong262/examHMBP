from django.db import migrations


def seed_sample_documents(apps, schema_editor):
    DocumentCategory = apps.get_model('documents', 'DocumentCategory')
    Document = apps.get_model('documents', 'Document')

    if DocumentCategory.objects.exists():
        return

    hr, _ = DocumentCategory.objects.get_or_create(
        slug='nhan-su',
        defaults={
            'name': 'Nhân sự',
            'description': 'Quy chế và chính sách nhân sự',
            'icon': 'bi-people-fill',
            'sort_order': 10,
            'is_active': True,
        },
    )
    ops, _ = DocumentCategory.objects.get_or_create(
        slug='van-hanh',
        defaults={
            'name': 'Vận hành',
            'description': 'Quy trình vận hành xưởng',
            'icon': 'bi-gear-wide-connected',
            'sort_order': 20,
            'is_active': True,
        },
    )

    Document.objects.get_or_create(
        category=hr,
        slug='quy-che-luong',
        defaults={
            'title': 'Quy chế lương',
            'summary': 'Chính sách lương, phụ cấp và thưởng',
            'content_type': 'TEXT',
            'body': (
                '<h3>Quy chế lương</h3>'
                '<p>Nội dung quy chế lương — HR cập nhật chi tiết tại đây.</p>'
                '<ul><li>Nguyên tắc tính lương</li><li>Phụ cấp ca / KPI</li><li>Thời hạn chi trả</li></ul>'
            ),
            'sort_order': 10,
            'is_active': True,
        },
    )
    Document.objects.get_or_create(
        category=hr,
        slug='quy-che-di-tre-ve-som',
        defaults={
            'title': 'Quy chế đi trễ về sớm',
            'summary': 'Quy định chấm công và xử lý vi phạm',
            'content_type': 'TEXT',
            'body': (
                '<h3>Quy chế đi trễ — về sớm</h3>'
                '<p>Quy định về giờ làm việc, đi trễ, về sớm và xin phép nghỉ.</p>'
            ),
            'sort_order': 20,
            'is_active': True,
        },
    )
    Document.objects.get_or_create(
        category=ops,
        slug='quy-trinh-an-toan',
        defaults={
            'title': 'Quy trình an toàn lao động',
            'summary': 'Hướng dẫn an toàn khi làm việc tại xưởng',
            'content_type': 'TEXT',
            'body': '<p>Nội dung quy trình an toàn — bộ phận HSE cập nhật.</p>',
            'sort_order': 10,
            'is_active': True,
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_sample_documents, noop),
    ]
