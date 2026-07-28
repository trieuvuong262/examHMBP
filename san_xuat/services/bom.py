"""BOM lifecycle: tạo phiên bản, đảm bảo tối đa 1 active / hồ sơ."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.products import resolve_product_ref


class BomError(Exception):
    pass


def get_active_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    return (
        tech_doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE)
        .prefetch_related('lines__material', 'process_steps')
        .first()
    )


def get_working_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    """Ưu tiên BOM active; nếu không có thì lấy draft mới nhất."""
    active = get_active_bom(tech_doc)
    if active:
        return active
    return (
        tech_doc.bom_versions.filter(status=BomVersion.STATUS_DRAFT)
        .prefetch_related('lines__material', 'process_steps')
        .order_by('-created_at')
        .first()
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
    """Chuyển BOM sang active; archive các bản active khác cùng hồ sơ."""
    tech_doc = bom.tech_doc
    tech_doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE).exclude(pk=bom.pk).update(
        status=BomVersion.STATUS_ARCHIVED,
    )
    bom.status = BomVersion.STATUS_ACTIVE
    bom.activated_at = timezone.now()
    bom.save(update_fields=['status', 'activated_at', 'updated_at'])
    return bom


@transaction.atomic
def ensure_single_active(tech_doc: ProductTechDoc) -> None:
    """Sửa dữ liệu lệch: giữ BOM active mới nhất, archive phần còn lại."""
    actives = list(
        tech_doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE).order_by('-activated_at', '-id'),
    )
    if len(actives) <= 1:
        return
    keep = actives[0]
    tech_doc.bom_versions.filter(
        status=BomVersion.STATUS_ACTIVE,
    ).exclude(pk=keep.pk).update(status=BomVersion.STATUS_ARCHIVED)


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
