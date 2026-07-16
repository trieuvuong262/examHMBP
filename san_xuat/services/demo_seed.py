"""Seed dữ liệu demo module Sản xuất (hồ sơ / BOM / quy trình / costing).

Không tạo mirror KiotViet, không tạo NVL, không nhập/xuất kho NPL.
Chỉ đọc mã SP từ mirror KV và NVL đã có trong danh mục kho_npl.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from kho_npl.models import Material
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.bom import BomError, activate_bom, create_tech_doc
from san_xuat.services.costing import save_costing_snapshot
from san_xuat.services.products import resolve_kv_product_ref

DEMO_NOTE_PREFIX = '[DEMO SX]'

# Định mức mẫu — chỉ gắn NVL đã có sẵn trong danh mục (không tạo Material).
SPORTSWEAR_BOM_LINES: list[tuple[str, Decimal, Decimal, int]] = [
    ('JP-VAI-COT180-WHT', Decimal('1.2000'), Decimal('5'), 10),
    ('JP-CHI-PES40-WHT', Decimal('1.0000'), Decimal('0'), 20),
    ('JP-TEM-SIZE-JP', Decimal('1.0000'), Decimal('0'), 30),
    ('JP-TUI-OPP-30x40', Decimal('1.0000'), Decimal('0'), 40),
]

SPORTSWEAR_PROCESS_STEPS: list[tuple[int, str, Decimal, Decimal]] = [
    (10, 'Cắt vải theo rập', Decimal('20'), Decimal('45000')),
    (20, 'May thân áo', Decimal('8'), Decimal('35000')),
    (30, 'In / thêu logo', Decimal('12'), Decimal('40000')),
    (40, 'QC thành phẩm', Decimal('30'), Decimal('30000')),
    (50, 'Ủi — đóng gói', Decimal('25'), Decimal('30000')),
]

DEFAULT_OVERHEAD_PCT = Decimal('5')

PREFERRED_PRODUCT_CODES = (
    'SP008073',
    'SP008074',
    'SP008075',
    'SP008076',
    'SP008077',
)


def demo_note_suffix(product_name: str = '') -> str:
    name = (product_name or '').strip()
    if name:
        return f'{DEMO_NOTE_PREFIX} Hồ sơ demo sportswear — {name}'
    return f'{DEMO_NOTE_PREFIX} Hồ sơ demo sportswear'


def is_demo_tech_doc(doc: ProductTechDoc) -> bool:
    return (doc.notes or '').startswith(DEMO_NOTE_PREFIX)


def resolve_existing_material(code: str) -> Material | None:
    """Tìm NVL trong danh mục — thử vài biến thể mã, không tạo mới."""
    raw = (code or '').strip()
    if not raw:
        return None
    candidates: list[str] = [raw]
    if raw.startswith('JP-'):
        candidates.append(raw[3:])
    else:
        candidates.append(f'JP-{raw}')
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        material = Material.objects.filter(code=candidate, is_active=True).first()
        if material:
            return material
    return None


def discover_kv_product_codes(*, limit: int = 5, prefer: tuple[str, ...] = PREFERRED_PRODUCT_CODES) -> list[str]:
    """Lấy mã SP từ mirror KiotViet (chỉ đọc)."""
    codes: list[str] = []
    seen: set[str] = set()

    for code in prefer:
        c = (code or '').strip()
        if not c or c in seen:
            continue
        if resolve_kv_product_ref(c):
            codes.append(c)
            seen.add(c)
        if len(codes) >= limit:
            return codes

    try:
        from kiotviet.models import KvProduct
        from kiotviet.sync_service import current_retailer
    except ImportError:
        return codes

    retailer = current_retailer()
    qs = (
        KvProduct.objects.filter(retailer=retailer, is_deleted=False)
        .exclude(code='')
        .order_by('code')
    )
    for product in qs.iterator():
        code = (product.code or '').strip()
        if not code or code in seen:
            continue
        if not code.upper().startswith('SP'):
            continue
        codes.append(code)
        seen.add(code)
        if len(codes) >= limit:
            break
    return codes


@transaction.atomic
def clear_demo_tech_docs() -> int:
    deleted, _ = ProductTechDoc.objects.filter(notes__startswith=DEMO_NOTE_PREFIX).delete()
    return deleted


@transaction.atomic
def seed_demo_tech_doc(
    product_code: str,
    *,
    user=None,
    activate: bool = True,
    costing: bool = True,
    force_lines: bool = False,
    adopt_existing: bool = False,
    overhead_pct: Decimal = DEFAULT_OVERHEAD_PCT,
) -> tuple[ProductTechDoc, BomVersion, dict]:
    """
    Tạo/cập nhật một hồ sơ demo. Trả (doc, bom, stats).
    stats: {bom_lines, process_steps, skipped_materials, costing_saved}
    """
    code = (product_code or '').strip()
    if not code:
        raise BomError('Thiếu mã sản phẩm.')

    ref = resolve_kv_product_ref(code)
    stats = {
        'bom_lines': 0,
        'process_steps': 0,
        'skipped_materials': [],
        'costing_saved': False,
        'created': False,
    }

    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    if doc and not is_demo_tech_doc(doc) and not adopt_existing:
        raise BomError(
            f'Hồ sơ {code} đã tồn tại và không phải demo ({DEMO_NOTE_PREFIX}). '
            f'Dùng --adopt để gắn nhãn demo và bổ sung BOM.',
        )

    if not doc:
        doc = create_tech_doc(product_code=code, user=user, create_draft_bom=True)
        stats['created'] = True
    elif ref:
        doc.product_name = ref.name or doc.product_name
        doc.product_image_url = ref.image_url or doc.product_image_url
        doc.kv_product_id = ref.kiotviet_id or doc.kv_product_id

    doc.notes = demo_note_suffix(ref.name if ref else doc.product_name)
    doc.is_active = True
    doc.save()

    bom = doc.bom_versions.filter(version_label='v1').first()
    if not bom:
        bom = BomVersion.objects.create(
            tech_doc=doc,
            version_label='v1',
            status=BomVersion.STATUS_DRAFT,
            overhead_pct=overhead_pct,
            created_by=user if getattr(user, 'is_authenticated', False) else None,
        )
    elif bom.overhead_pct != overhead_pct:
        bom.overhead_pct = overhead_pct
        bom.save(update_fields=['overhead_pct', 'updated_at'])

    if force_lines or not bom.lines.exists():
        if force_lines:
            bom.lines.all().delete()
        for material_code, qty, scrap, sort_order in SPORTSWEAR_BOM_LINES:
            material = resolve_existing_material(material_code)
            if not material:
                stats['skipped_materials'].append(material_code)
                continue
            BomLine.objects.create(
                bom=bom,
                material=material,
                qty=qty,
                scrap_pct=scrap,
                sort_order=sort_order,
            )
            stats['bom_lines'] += 1

    if force_lines or not bom.process_steps.exists():
        if force_lines:
            bom.process_steps.all().delete()
        for seq, name, norm, cost in SPORTSWEAR_PROCESS_STEPS:
            ProcessStep.objects.create(
                bom=bom,
                sequence=seq,
                process_name=name,
                norm_per_hour=norm,
                cost_per_hour=cost,
            )
            stats['process_steps'] += 1

    if activate and bom.status != BomVersion.STATUS_ACTIVE:
        activate_bom(bom)

    if costing:
        save_costing_snapshot(
            bom,
            user=user,
            notes=f'{DEMO_NOTE_PREFIX} Costing demo',
        )
        stats['costing_saved'] = True

    return doc, bom, stats


@transaction.atomic
def clear_all_san_xuat_demo() -> dict[str, int]:
    from san_xuat.services.demo_seed_hub import clear_demo_hub

    return {
        'hub': clear_demo_hub(),
        'tech_docs': clear_demo_tech_docs(),
    }
