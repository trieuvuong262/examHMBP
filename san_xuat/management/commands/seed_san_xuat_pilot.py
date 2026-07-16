from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from kho_npl.models import Material
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.bom import BomError, activate_bom, create_tech_doc
from san_xuat.services.products import resolve_kv_product_ref

PILOT_CODE = 'SP008073'

# Định mức mẫu — Kỹ thuật chỉnh sau khi có marker thật.
DEFAULT_BOM_LINES = [
    # material_code, qty, scrap_pct, sort_order, sample_base_price (nếu Material.base_price=0)
    ('JP-VAI-COT180-WHT', Decimal('1.2000'), Decimal('5'), 10, Decimal('45000')),
    ('JP-CHI-PES40-WHT', Decimal('1.0000'), Decimal('0'), 20, Decimal('2500')),
    ('JP-TEM-SIZE-JP', Decimal('1.0000'), Decimal('0'), 30, Decimal('800')),
    ('JP-TUI-OPP-30x40', Decimal('1.0000'), Decimal('0'), 40, Decimal('1200')),
]

DEFAULT_PROCESS_STEPS = [
    # sequence, name, norm/h, cost/h
    (10, 'Cắt vải theo rập', Decimal('20'), Decimal('45000')),
    (20, 'May thân áo', Decimal('8'), Decimal('35000')),
    (30, 'In / thêu logo', Decimal('12'), Decimal('40000')),
    (40, 'QC thành phẩm', Decimal('30'), Decimal('30000')),
    (50, 'Ủi — đóng gói', Decimal('25'), Decimal('30000')),
]


class Command(BaseCommand):
    help = f'Tạo hồ sơ SX pilot {PILOT_CODE} với BOM + công đoạn mẫu sportswear.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Kích hoạt BOM sau khi seed.',
        )
        parser.add_argument(
            '--force-lines',
            action='store_true',
            help='Xóa dòng BOM/công đoạn hiện có của v1 rồi ghi lại mẫu.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        ref = resolve_kv_product_ref(PILOT_CODE)
        if not ref:
            self.stderr.write(self.style.WARNING(
                f'Không thấy {PILOT_CODE} trên mirror KvProduct — vẫn tạo hồ sơ với tên trống.',
            ))
        else:
            self.stdout.write(f'KV: {ref.code} — {ref.name} | giá {ref.base_price}')

        doc = ProductTechDoc.objects.filter(product_code=PILOT_CODE).first()
        if not doc:
            try:
                doc = create_tech_doc(product_code=PILOT_CODE, create_draft_bom=True)
            except BomError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            self.stdout.write(self.style.SUCCESS(f'Tạo hồ sơ {doc.product_code}'))
        else:
            self.stdout.write(f'Hồ sơ đã có: {doc.pk}')
            if ref and (not doc.product_name or doc.kv_product_id is None):
                doc.product_name = ref.name
                doc.product_image_url = ref.image_url
                doc.kv_product_id = ref.kiotviet_id
                doc.save(update_fields=['product_name', 'product_image_url', 'kv_product_id', 'updated_at'])

        bom = doc.bom_versions.filter(version_label='v1').first()
        if not bom:
            bom = BomVersion.objects.create(
                tech_doc=doc,
                version_label='v1',
                status=BomVersion.STATUS_DRAFT,
                overhead_pct=Decimal('5'),
            )
            self.stdout.write('Tạo BOM v1')
        else:
            if bom.overhead_pct == 0:
                bom.overhead_pct = Decimal('5')
                bom.save(update_fields=['overhead_pct', 'updated_at'])

        if options['force_lines'] or not bom.lines.exists():
            if options['force_lines']:
                bom.lines.all().delete()
            added = 0
            for code, qty, scrap, sort_order, sample_price in DEFAULT_BOM_LINES:
                material = Material.objects.filter(code=code, is_active=True).first()
                if not material:
                    self.stderr.write(self.style.WARNING(f'Bỏ qua NPL thiếu: {code}'))
                    continue
                if (material.base_price or 0) <= 0 and sample_price > 0:
                    material.base_price = sample_price
                    material.save(update_fields=['base_price', 'updated_at'])
                    self.stdout.write(f'  Gán giá cơ bản mẫu {code} = {sample_price}')
                BomLine.objects.create(
                    bom=bom,
                    material=material,
                    qty=qty,
                    scrap_pct=scrap,
                    sort_order=sort_order,
                )
                added += 1
            self.stdout.write(f'Thêm {added} dòng BOM')
        else:
            # Bổ sung giá mẫu nếu dòng đã có nhưng NPL vẫn giá 0
            for code, _qty, _scrap, _sort, sample_price in DEFAULT_BOM_LINES:
                material = Material.objects.filter(code=code, is_active=True).first()
                if material and (material.base_price or 0) <= 0 and sample_price > 0:
                    material.base_price = sample_price
                    material.save(update_fields=['base_price', 'updated_at'])
                    self.stdout.write(f'  Gán giá cơ bản mẫu {code} = {sample_price}')

        if options['force_lines'] or not bom.process_steps.exists():
            if options['force_lines']:
                bom.process_steps.all().delete()
            for seq, name, norm, cost in DEFAULT_PROCESS_STEPS:
                ProcessStep.objects.create(
                    bom=bom,
                    sequence=seq,
                    process_name=name,
                    norm_per_hour=norm,
                    cost_per_hour=cost,
                )
            self.stdout.write(f'Thêm {len(DEFAULT_PROCESS_STEPS)} công đoạn')

        if options['activate']:
            activate_bom(bom)
            self.stdout.write(self.style.SUCCESS(f'Đã kích hoạt BOM {bom.version_label}'))

        self.stdout.write(self.style.SUCCESS(
            f'Xong. Mở /san-xuat/ho-so/{doc.pk}/',
        ))
