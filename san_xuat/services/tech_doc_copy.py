"""Copy BOM + OB từ hồ sơ thiết kế này, dán đè sang hồ sơ khác."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q

from san_xuat.ie_models import SxRouting, SxRoutingLine
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.bom import create_bom_version, get_working_bom
from san_xuat.services.ie_ops import (
    IeOpsError,
    create_blank_routing,
    is_routing_locked,
    norm_per_hour_from_smv_seconds,
    routing_line_smv_seconds,
)


SESSION_KEY = 'sx_bom_ob_clipboard'

_ZERO = Decimal('0')
_NORM_MIN = Decimal('0.01')


class TechDocCopyError(Exception):
    pass


@dataclass
class PasteResult:
    target_doc: ProductTechDoc
    bom: BomVersion | None
    routing: SxRouting | None
    n_bom_lines: int = 0
    n_ob_lines: int = 0
    bom_new_version: bool = False
    routing_new_version: bool = False


def is_bom_locked(bom: BomVersion | None) -> bool:
    """BOM đã gắn lệnh SX thì không sửa đè — tạo phiên bản mới."""
    if bom is None:
        return False
    return bom.production_orders.exists()


def clipboard_payload(*, doc: ProductTechDoc, bom: BomVersion | None, routing: SxRouting | None) -> dict:
    if bom is None and routing is None:
        raise TechDocCopyError('Hồ sơ chưa có BOM hoặc OB để sao chép.')
    return {
        'source_doc_id': doc.pk,
        'source_code': doc.product_code or '',
        'source_name': doc.product_name or '',
        'bom_id': bom.pk if bom else None,
        'bom_label': (bom.version_label if bom else '') or '',
        'routing_id': routing.pk if routing else None,
        'routing_rev': (routing.routing_rev if routing else '') or '',
        'n_bom_lines': bom.lines.count() if bom else 0,
        'n_ob_lines': routing.lines.count() if routing else 0,
    }


def write_clipboard(request, *, doc: ProductTechDoc, bom: BomVersion | None, routing: SxRouting | None) -> dict:
    payload = clipboard_payload(doc=doc, bom=bom, routing=routing)
    request.session[SESSION_KEY] = payload
    request.session.modified = True
    return payload


def read_clipboard(request) -> dict | None:
    data = request.session.get(SESSION_KEY)
    if not isinstance(data, dict) or not data.get('source_doc_id'):
        return None
    return data


def load_clipboard_sources(data: dict | None) -> tuple[ProductTechDoc, BomVersion | None, SxRouting | None]:
    if not data:
        raise TechDocCopyError('Chưa sao chép BOM/OB. Mở hồ sơ nguồn rồi bấm Sao chép.')
    try:
        source_doc = ProductTechDoc.objects.get(pk=int(data['source_doc_id']))
    except (TypeError, ValueError, ProductTechDoc.DoesNotExist) as exc:
        raise TechDocCopyError('Hồ sơ nguồn không còn tồn tại.') from exc

    bom = None
    bom_id = data.get('bom_id')
    if bom_id:
        bom = BomVersion.objects.filter(pk=int(bom_id), tech_doc=source_doc).first()
        if bom is None:
            raise TechDocCopyError('Phiên bản BOM đã copy không còn tồn tại.')

    routing = None
    routing_id = data.get('routing_id')
    if routing_id:
        routing = (
            SxRouting.objects.filter(
                Q(tech_doc=source_doc) | Q(bom_versions__tech_doc=source_doc),
                pk=int(routing_id),
            )
            .distinct()
            .first()
        )
        if routing is None:
            raise TechDocCopyError('Phiên bản OB đã copy không còn tồn tại.')

    if bom is None and routing is None:
        raise TechDocCopyError('Clipboard không có BOM hoặc OB hợp lệ.')
    return source_doc, bom, routing


def resolve_doc_routing(doc: ProductTechDoc, *, routing_id: str | int | None = None, bom: BomVersion | None = None):
    qs = (
        SxRouting.objects.filter(Q(tech_doc=doc) | Q(bom_versions__tech_doc=doc))
        .distinct()
        .annotate(n_lines=Count('lines', distinct=True))
        .order_by('routing_rev', 'pk')
    )
    items = list(qs)
    if routing_id is not None and str(routing_id).isdigit():
        hit = next((item for item in items if item.pk == int(routing_id)), None)
        if hit is not None:
            return hit
    if bom and bom.routing_id:
        hit = next((item for item in items if item.pk == bom.routing_id), None)
        if hit is not None:
            return hit
    return items[-1] if items else None


def _copy_bom_lines(source: BomVersion, target: BomVersion) -> int:
    target.overhead_pct = source.overhead_pct
    target.overhead_amount = source.overhead_amount
    src_code = source.tech_doc.product_code
    copied = f'Sao chép từ {src_code} / {source.version_label}'
    target.notes = (source.notes or '').strip() or copied
    target.save(update_fields=['overhead_pct', 'overhead_amount', 'notes', 'updated_at'])
    target.lines.all().delete()
    n = 0
    for line in source.lines.order_by('sort_order', 'id'):
        BomLine.objects.create(
            bom=target,
            material=line.material,
            substitute_material=line.substitute_material,
            qty=line.qty,
            scrap_pct=line.scrap_pct,
            size_code=line.size_code,
            notes=line.notes,
            sort_order=line.sort_order,
        )
        n += 1
    return n


def _routing_line_kwargs(line: SxRoutingLine) -> dict:
    return {
        'seq_no': line.seq_no,
        'operation': line.operation,
        'op_code': line.op_code,
        'op_rev': line.op_rev,
        'op_name_vi': line.op_name_vi,
        'group_code': line.group_code,
        'qty_per_garment': line.qty_per_garment,
        'library_unit_smv': line.library_unit_smv,
        'applied_unit_smv': line.applied_unit_smv,
        'price_factor': line.price_factor,
        'total_unit_price': line.total_unit_price,
        'machine': line.machine,
        'machine_code': line.machine_code,
        'work_center': line.work_center,
        'work_center_code': line.work_center_code,
        'count_minutes': line.count_minutes,
        'transfer_minutes': line.transfer_minutes,
        'predecessor_seq': line.predecessor_seq,
        'parallel_group': line.parallel_group,
        'bundle_size': line.bundle_size,
        'skill_level_label': line.skill_level_label,
        'critical_qc': line.critical_qc,
        'target_efficiency': line.target_efficiency,
        'notes': line.notes,
        'variance_explanation': line.variance_explanation,
    }


def _copy_routing_lines(source: SxRouting, target: SxRouting) -> dict[int, SxRoutingLine]:
    mapping: dict[int, SxRoutingLine] = {}
    for line in source.lines.order_by('seq_no', 'id'):
        created = SxRoutingLine.objects.create(routing=target, **_routing_line_kwargs(line))
        mapping[line.pk] = created
    return mapping


def _reset_routing_approval(routing: SxRouting) -> None:
    routing.approval_status = SxRouting.APPROVAL_DRAFT
    routing.approved_by = ''
    routing.approved_at = None
    routing.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'updated_at'])


def _rebuild_process_steps_from_routing(bom: BomVersion, routing: SxRouting) -> int:
    n = 0
    for line in routing.lines.select_related('operation', 'work_center').order_by('seq_no', 'pk'):
        smv = routing_line_smv_seconds(line, prefer_applied=True)
        norm = norm_per_hour_from_smv_seconds(smv)
        ProcessStep.objects.create(
            bom=bom,
            sequence=line.seq_no or 10,
            process_name=(line.op_name_vi or line.op_code or '')[:120],
            operation=line.operation,
            op_code=(line.op_code or '')[:30],
            routing_line=line,
            norm_per_hour=max(norm, _NORM_MIN),
            cost_per_hour=line.price_factor or _ZERO,
            std_time_minutes=(smv / Decimal('60')).quantize(Decimal('0.01')) if smv > 0 else _ZERO,
            work_center=line.work_center,
            count_minutes=line.count_minutes or _ZERO,
            transfer_minutes=line.transfer_minutes or _ZERO,
            notes=(line.notes or f'Routing {routing.routing_id}')[:255],
        )
        n += 1
    return n


def _copy_process_steps(
    source_bom: BomVersion,
    target_bom: BomVersion,
    *,
    line_map: dict[int, SxRoutingLine] | None = None,
    target_routing: SxRouting | None = None,
) -> int:
    source_steps = list(source_bom.process_steps.select_related('routing_line').order_by('sequence', 'id'))
    if not source_steps:
        if target_routing is not None:
            return _rebuild_process_steps_from_routing(target_bom, target_routing)
        return 0
    n = 0
    for step in source_steps:
        new_rl = None
        if line_map and step.routing_line_id:
            new_rl = line_map.get(step.routing_line_id)
        if new_rl is None and target_routing is not None:
            new_rl = target_routing.lines.filter(seq_no=step.sequence).first()
        ProcessStep.objects.create(
            bom=target_bom,
            sequence=step.sequence,
            process_name=step.process_name,
            operation=step.operation,
            op_code=step.op_code,
            routing_line=new_rl,
            norm_per_hour=max(step.norm_per_hour or _ZERO, _NORM_MIN),
            cost_per_hour=step.cost_per_hour or _ZERO,
            piece_rate=step.piece_rate or _ZERO,
            std_time_minutes=step.std_time_minutes or _ZERO,
            work_center=step.work_center,
            count_minutes=step.count_minutes or _ZERO,
            transfer_minutes=step.transfer_minutes or _ZERO,
            notes=step.notes,
        )
        n += 1
    return n


@transaction.atomic
def paste_bom_and_ob(
    *,
    source_doc: ProductTechDoc,
    source_bom: BomVersion | None,
    source_routing: SxRouting | None,
    target_doc: ProductTechDoc,
    target_bom: BomVersion | None = None,
    target_routing: SxRouting | None = None,
    user=None,
) -> PasteResult:
    if source_doc.pk == target_doc.pk:
        raise TechDocCopyError('Chọn hồ sơ thiết kế khác — không dán đè lên chính hồ sơ đang copy.')
    if source_bom is None and source_routing is None:
        raise TechDocCopyError('Không có BOM hoặc OB để dán.')

    result = PasteResult(target_doc=target_doc, bom=target_bom, routing=target_routing)
    line_map: dict[int, SxRoutingLine] = {}

    if source_bom is not None:
        if target_bom is None:
            target_bom = get_working_bom(target_doc)
        if target_bom is None:
            target_bom = create_bom_version(target_doc, user=user)
            result.bom_new_version = True
        elif is_bom_locked(target_bom):
            target_bom = create_bom_version(target_doc, user=user)
            result.bom_new_version = True
        result.n_bom_lines = _copy_bom_lines(source_bom, target_bom)
        result.bom = target_bom

    if source_routing is not None:
        if target_routing is None:
            target_routing = resolve_doc_routing(target_doc, bom=target_bom)
        try:
            if target_routing is None:
                target_routing = create_blank_routing(tech_doc=target_doc, user=user)
                result.routing_new_version = True
            elif is_routing_locked(target_routing):
                target_routing = create_blank_routing(tech_doc=target_doc, user=user)
                result.routing_new_version = True
            else:
                if target_bom is not None:
                    target_bom.process_steps.filter(routing_line__routing=target_routing).update(
                        routing_line=None,
                    )
                target_routing.lines.all().delete()
                _reset_routing_approval(target_routing)
        except IeOpsError as exc:
            raise TechDocCopyError(str(exc)) from exc
        line_map = _copy_routing_lines(source_routing, target_routing)
        result.n_ob_lines = len(line_map)
        result.routing = target_routing

    target_bom = result.bom
    target_routing = result.routing
    copied_ob = source_routing is not None and target_routing is not None
    if copied_ob and target_bom is not None and target_bom.routing_id != target_routing.pk:
        target_bom.routing = target_routing
        target_bom.save(update_fields=['routing', 'updated_at'])

    if target_bom is not None:
        target_bom.process_steps.all().delete()
        if source_bom is not None:
            _copy_process_steps(
                source_bom,
                target_bom,
                line_map=line_map if copied_ob else None,
                target_routing=target_routing if copied_ob else None,
            )
        elif copied_ob:
            _rebuild_process_steps_from_routing(target_bom, target_routing)

    return result
