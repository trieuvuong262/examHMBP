"""Vòng đời BOM: nhiều phiên bản, tối đa một bản đang áp dụng mỗi hồ sơ."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.products import resolve_product_ref


class BomError(Exception):
    pass


def get_active_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    """BOM đang áp dụng của hồ sơ."""
    return (
        tech_doc.bom_versions.prefetch_related('lines__material', 'process_steps')
        .filter(status=BomVersion.STATUS_ACTIVE)
        .order_by('-activated_at', '-updated_at', '-id')
        .first()
    )


def get_working_bom(tech_doc: ProductTechDoc) -> BomVersion | None:
    """Ưu tiên bản đang áp dụng; nếu chưa có thì lấy bản chưa ngừng mới nhất."""
    active = get_active_bom(tech_doc)
    if active is not None:
        return active
    working = (
        tech_doc.bom_versions.prefetch_related('lines__material', 'process_steps')
        .exclude(status=BomVersion.STATUS_ARCHIVED)
        .order_by('-created_at', '-id')
        .first()
    )
    if working is not None:
        return working
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
    """Đưa một BOM vào áp dụng và ngừng bản đang áp dụng trước đó."""
    return set_bom_status(bom, BomVersion.STATUS_ACTIVE)


@transaction.atomic
def set_bom_status(bom: BomVersion, status: str) -> BomVersion:
    """Đổi trạng thái BOM, bảo đảm mỗi hồ sơ chỉ có một bản đang áp dụng."""
    allowed = {value for value, _label in BomVersion.STATUS_CHOICES}
    if status not in allowed:
        raise BomError('Trạng thái BOM không hợp lệ.')

    locked = BomVersion.objects.select_for_update().get(pk=bom.pk)
    if status == BomVersion.STATUS_ACTIVE:
        (
            BomVersion.objects.select_for_update()
            .filter(tech_doc_id=locked.tech_doc_id, status=BomVersion.STATUS_ACTIVE)
            .exclude(pk=locked.pk)
            .update(status=BomVersion.STATUS_ARCHIVED)
        )
        locked.activated_at = timezone.now()
    locked.status = status
    locked.save(update_fields=['status', 'activated_at', 'updated_at'])
    return locked


@transaction.atomic
def ensure_single_active(tech_doc: ProductTechDoc) -> None:
    """Giữ bản active mới nhất và ngừng các bản active còn lại."""
    active_ids = list(
        tech_doc.bom_versions.select_for_update()
        .filter(status=BomVersion.STATUS_ACTIVE)
        .order_by('-activated_at', '-updated_at', '-id')
        .values_list('pk', flat=True)
    )
    if len(active_ids) > 1:
        tech_doc.bom_versions.filter(pk__in=active_ids[1:]).update(
            status=BomVersion.STATUS_ARCHIVED,
        )


@transaction.atomic
def delete_bom_version(bom: BomVersion) -> str:
    """Xóa phiên bản BOM nếu chưa được dùng trên lệnh sản xuất."""
    if bom is None:
        raise BomError('Không tìm thấy phiên bản BOM.')
    locked = BomVersion.objects.select_for_update().get(pk=bom.pk)
    if locked.production_orders.exists():
        raise BomError(
            f'Không thể xóa BOM {locked.version_label}: phiên bản đang được dùng trên lệnh SX.'
        )
    label = locked.version_label
    locked.delete()
    return label


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
        overhead_amount=copy_from.overhead_amount if copy_from else 0,
        other_cost_amount=copy_from.other_cost_amount if copy_from else 0,
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
                operation=step.operation,
                op_code=step.op_code,
                routing_line=step.routing_line,
                norm_per_hour=step.norm_per_hour,
                cost_per_hour=step.cost_per_hour,
                piece_rate=step.piece_rate,
                std_time_minutes=step.std_time_minutes,
                work_center=step.work_center,
                notes=step.notes,
            )
    return bom
