# Generated manually for IE settings catalogs

from django.db import migrations, models


def seed_smv_basis_and_stages(apps, schema_editor):
    SxSmvBasis = apps.get_model('san_xuat', 'SxSmvBasis')
    SxProcessStage = apps.get_model('san_xuat', 'SxProcessStage')
    SxOperation = apps.get_model('san_xuat', 'SxOperation')
    SxOperationGroup = apps.get_model('san_xuat', 'SxOperationGroup')

    for code, name, order in (
        ('MIN', 'Phút/SP', 10),
        ('SEC', 'Giây', 20),
        ('PCS_H', 'SP/H', 30),
    ):
        SxSmvBasis.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )

    for order, label in enumerate(
        sorted({
            (v or '').strip()
            for v in SxOperation.objects.exclude(smv_basis='').values_list('smv_basis', flat=True)
            if (v or '').strip()
        }),
        start=1,
    ):
        existing = SxSmvBasis.objects.filter(name__iexact=label).first() or SxSmvBasis.objects.filter(
            code__iexact=label[:40]
        ).first()
        if existing:
            continue
        code = label[:40]
        base = code
        n = 1
        while SxSmvBasis.objects.filter(code=code).exists():
            n += 1
            code = f'{base[:36]}_{n}'
        SxSmvBasis.objects.create(
            code=code,
            name=label[:150],
            sort_order=100 + order * 10,
            is_active=True,
        )

    for code, name, order in (
        ('CUT', 'Cắt', 10),
        ('SEW', 'May lắp ráp', 20),
        ('FINISH', 'Hoàn thiện', 30),
    ):
        SxProcessStage.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )

    labels = set()
    for val in SxOperation.objects.exclude(process_stage_label='').values_list('process_stage_label', flat=True):
        labels.add((val or '').strip())
    for val in SxOperationGroup.objects.exclude(process_stage_label='').values_list(
        'process_stage_label', flat=True
    ):
        labels.add((val or '').strip())
    labels.discard('')
    for order, label in enumerate(sorted(labels), start=1):
        if SxProcessStage.objects.filter(name__iexact=label).exists():
            continue
        if SxProcessStage.objects.filter(code__iexact=label[:40]).exists():
            continue
        code = label[:40]
        base = code
        n = 1
        while SxProcessStage.objects.filter(code=code).exists():
            n += 1
            code = f'{base[:36]}_{n}'
        SxProcessStage.objects.create(
            code=code,
            name=label[:150],
            sort_order=100 + order * 10,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('san_xuat', '0065_product_part_catalog'),
    ]

    operations = [
        migrations.CreateModel(
            name='SxSmvBasis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=40, unique=True, verbose_name='Mã')),
                ('name', models.CharField(max_length=150, verbose_name='Tên')),
                ('sort_order', models.PositiveSmallIntegerField(db_index=True, default=100, verbose_name='Thứ tự')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Đang dùng')),
                ('notes', models.CharField(blank=True, default='', max_length=255, verbose_name='Ghi chú')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Đơn vị cơ sở SMV',
                'verbose_name_plural': 'Đơn vị cơ sở SMV',
                'ordering': ['sort_order', 'code'],
                'abstract': False,
            },
        ),
        migrations.RunPython(seed_smv_basis_and_stages, migrations.RunPython.noop),
    ]
