from django.db import migrations

# Bộ khâu legacy do migration 0066 seed. 'CUT' trùng tên 'Cắt' với khâu thật 'CAT'
# nên dropdown Khâu sản xuất hiện hai mục giống nhau.
LEGACY_STAGE_CODES = ('CUT', 'SEW', 'FINISH')

CANONICAL_STAGES = (
    ('CAT', 'Cắt', 10),
    ('IN_EP', 'In - Ép', 20),
    ('THEU', 'Thêu', 30),
    ('MAY', 'May', 40),
    ('HT', 'Ủi - Gấp xếp', 50),
    ('GH', 'Giao hàng thành phẩm', 60),
)


def forwards(apps, schema_editor):
    SxProcessStage = apps.get_model('san_xuat', 'SxProcessStage')
    SxOperationGroup = apps.get_model('san_xuat', 'SxOperationGroup')

    for code, name, order in CANONICAL_STAGES:
        SxProcessStage.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )

    canonical_by_name = {
        name: SxProcessStage.objects.filter(code=code).first()
        for code, name, _ in CANONICAL_STAGES
    }

    for stage in SxProcessStage.objects.filter(code__in=LEGACY_STAGE_CODES):
        replacement = canonical_by_name.get(stage.name)
        groups = SxOperationGroup.objects.filter(process_stage=stage)
        if replacement is not None:
            groups.update(process_stage=replacement)
        elif groups.exists():
            # Không có khâu chuẩn tương ứng — giữ bản ghi, chỉ tắt để không hiện trong dropdown.
            if stage.is_active:
                stage.is_active = False
                stage.save(update_fields=['is_active'])
            continue
        stage.delete()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0079_sxteampersonnelskill_process_avg_qty'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
