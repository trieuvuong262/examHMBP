"""BOM lifecycle: nhiều phiên bản ngang hàng trên cùng hồ sơ SX.

Mỗi version (vd. Nội bộ / Gia công) đều dùng được — không còn mô hình
1 bản «đang dùng» và các bản còn lại bị lưu trữ.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.products import resolve_product_ref


class BomError(Exception):
    pass


def get_active_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    """BOM mặc định khi không chỉ định — lấy bản mới nhất (mọi version ngang hàng)."""
    return get_working_bom(tech_doc)


def get_working_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    """Bản BOM mới nhất của hồ sơ (các version ngang hàng)."""
    return (
        tech_doc.bom_versions.prefetch_related('lines__material', 'process_steps')
        .order_by('-created_at', '-id')
        .first()
    )


def list_bom_versions(tech_doc: ProductTechDoc):
    return tech_doc.bom_versions.prefetch_related('lines__material', 'process_steps').order_by(
        'created_at', 'id'
    )


@transaction.atomic
def create_tech_doc(
    *,
    product_code: str,
    user=None,
    notes: str = '',
    create_draft_bom: bool = True,
) -> ProductTechDoc:
    code = (product_code or '').strip()
    if not code:
        raise BomError('Thiếu mã sản phẩm.')

    ref = resolve_product_ref(code)
    if not ref:
        raise BomError(f'Mã {code} không có trong kho sản phẩm.')
    code = ref.code

    if ProductTechDoc.objects.filter(product_code__iexact=code).exists():
        raise BomError(f'Hồ sơ SX cho mã {code} đã tồn tại.')

    doc = ProductTechDoc(
        product_code=code,
        product_name=ref.name or '',
        product_image_url=ref.image_url or '',
        kv_product_id=ref.kiotviet_id,
        notes=notes or '',
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    doc.save()
    if create_draft_bom:
        BomVersion.objects.create(
            tech_doc=doc,
            version_label='v1',
            status=BomVersion.STATUS_DRAFT,
            created_by=user if getattr(user, 'is_authenticated', False) else None,
        )
    return doc


@transaction.atomic
def activate_bom(bom: BomVersion) -> BomVersion:
    """Giữ API cũ — không archive các version khác (các bản ngang hàng)."""
    if not bom.activated_at:
        bom.activated_at = timezone.now()
        bom.save(update_fields=['activated_at', 'updated_at'])
    return bom


@transaction.atomic
def ensure_single_active(tech_doc: ProductTechDoc) -> None:
    """Không còn ép 1 active — giữ hàm để tương thích chỗ gọi cũ."""
    return


def next_version_label(tech_doc: ProductTechDoc) -> str:
    n = tech_doc.bom_versions.count() + 1
    return f'v{n}'


@transaction.atomic
def create_bom_version(
    tech_doc: ProductTechDoc,
    *,
    version_label: str | None = None,
    user=None,
    copy_from: BomVersion | None = None,
) -> BomVersion:
    label = (version_label or next_version_label(tech_doc)).strip()
    if tech_doc.bom_versions.filter(version_label=label).exists():
        raise BomError(f'Phiên bản {label} đã tồn tại.')
    bom = BomVersion.objects.create(
        tech_doc=tech_doc,
        version_label=label,
        status=BomVersion.STATUS_DRAFT,
        overhead_pct=copy_from.overhead_pct if copy_from else 0,
        notes=copy_from.notes if copy_from else '',
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    if copy_from:
        from san_xuat.models import BomLine, ProcessStep

        for line in copy_from.lines.all():
            BomLine.objects.create(
                bom=bom,
                material=line.material,
                qty=line.qty,
                scrap_pct=line.scrap_pct,
                size_code=line.size_code,
                notes=line.notes,
                sort_order=line.sort_order,
            )
        for step in copy_from.process_steps.all():
            ProcessStep.objects.create(
                bom=bom,
                sequence=step.sequence,
                process_name=step.process_name,
                norm_per_hour=step.norm_per_hour,
                cost_per_hour=step.cost_per_hour,
                notes=step.notes,
            )
    return bom
