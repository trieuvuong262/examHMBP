"""Copy/dán BOM và OB riêng trên hồ sơ thiết kế — clipboard không gộp chung."""

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


SESSION_KEY_BOM = 'sx_bom_clipboard'
SESSION_KEY_OB = 'sx_ob_clipboard'

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
    bom_pasted: bool = False
    ob_pasted: bool = False


def is_bom_locked(bom: BomVersion | None) -> bool:
    """BOM đã gắn lệnh SX thì không sửa đè — tạo phiên bản mới."""
    if bom is None:
        return False
    return bom.production_orders.exists()


def _source_meta(doc: ProductTechDoc) -> dict:
    return {
        'source_doc_id': doc.pk,
        'source_code': doc.product_code or '',
        'source_name': doc.product_name or '',
    }


def bom_clipboard_payload(*, doc: ProductTechDoc, bom: BomVersion | None) -> dict:
    if bom is None:
        raise TechDocCopyError('Hồ sơ chưa có BOM để sao chép.')
    return {
        **_source_meta(doc),
        'kind': 'bom',
        'bom_id': bom.pk,
        'bom_label': (bom.version_label or ''),
        'n_bom_lines': bom.lines.count(),
    }


def ob_clipboard_payload(
    *,
    doc: ProductTechDoc,
    routing: SxRouting | None,
    process_bom: BomVersion | None = None,
) -> dict:
    if routing is None:
        raise TechDocCopyError('Hồ sơ chưa có OB để sao chép.')
    return {
        **_source_meta(doc),
        'kind': 'ob',
        'routing_id': routing.pk,
        'routing_rev': (routing.routing_rev or ''),
        'n_ob_lines': routing.lines.count(),
        'process_bom_id': process_bom.pk if process_bom else None,
    }


def _write_session(request, key: str, payload: dict) -> dict:
    request.session[key] = payload
    request.session.modified = True
    return payload


def write_bom_clipboard(request, *, doc: ProductTechDoc, bom: BomVersion | None) -> dict:
    return _write_session(request, SESSION_KEY_BOM, bom_clipboard_payload(doc=doc, bom=bom))


def write_ob_clipboard(
    request,
    *,
    doc: ProductTechDoc,
    routing: SxRouting | None,
    process_bom: BomVersion | None = None,
) -> dict:
    return _write_session(
        request,
        SESSION_KEY_OB,
        ob_clipboard_payload(doc=doc, routing=routing, process_bom=process_bom),
    )


def _read_session(request, key: str) -> dict | None:
    data = request.session.get(key)
    if not isinstance(data, dict) or not data.get('source_doc_id'):
        return None
    return data


def read_bom_clipboard(request) -> dict | None:
    data = _read_session(request, SESSION_KEY_BOM)
    if data and data.get('kind') not in (None, 'bom'):
        return None
    if data and not data.get('bom_id'):
        return None
    return data


def read_ob_clipboard(request) -> dict | None:
    data = _read_session(request, SESSION_KEY_OB)
    if data and data.get('kind') not in (None, 'ob'):
        return None
    if data and not data.get('routing_id'):
        return None
    return data


def _load_source_doc(data: dict | None, *, empty_message: str) -> ProductTechDoc:
    if not data:
        raise TechDocCopyError(empty_message)
    try:
        return ProductTechDoc.objects.get(pk=int(data['source_doc_id']))
    except (TypeError, ValueError, ProductTechDoc.DoesNotExist) as exc:
        raise TechDocCopyError('Hồ sơ nguồn không còn tồn tại.') from exc


def load_bom_clipboard_source(data: dict | None) -> tuple[ProductTechDoc, BomVersion]:
    source_doc = _load_source_doc(data, empty_message='Chưa sao chép BOM. Mở hồ sơ nguồn (tab BOM) rồi bấm Sao chép.')
    try:
        bom = BomVersion.objects.filter(pk=int(data['bom_id']), tech_doc=source_doc).first()
    except (TypeError, ValueError, KeyError) as exc:
        raise TechDocCopyError('Clipboard BOM không hợp lệ.') from exc
    if bom is None:
        raise TechDocCopyError('Phiên bản BOM đã copy không còn tồn tại.')
    return source_doc, bom


def _resolve_source_routing(source_doc: ProductTechDoc, routing_id) -> SxRouting:
    try:
        routing = (
            SxRouting.objects.filter(
                Q(tech_doc=source_doc) | Q(bom_versions__tech_doc=source_doc),
                pk=int(routing_id),
            )
            .distinct()
            .first()
        )
    except (TypeError, ValueError) as exc:
        raise TechDocCopyError('Clipboard OB không hợp lệ.') from exc
    if routing is None:
        raise TechDocCopyError('Phiên bản OB đã copy không còn tồn tại.')
    return routing


def _process_bom_for_routing(
    source_doc: ProductTechDoc,
    routing: SxRouting,
    *,
    process_bom_id=None,
) -> BomVersion | None:
    if process_bom_id:
        try:
            hit = BomVersion.objects.filter(pk=int(process_bom_id), tech_doc=source_doc).first()
        except (TypeError, ValueError):
            hit = None
        if hit is not None:
            return hit
    return (
        BomVersion.objects.filter(tech_doc=source_doc, routing=routing)
        .order_by('-id')
        .first()
    )


def load_ob_clipboard_source(data: dict | None) -> tuple[ProductTechDoc, SxRouting, BomVersion | None]:
    source_doc = _load_source_doc(data, empty_message='Chưa sao chép OB. Mở hồ sơ nguồn (tab OB) rồi bấm Sao chép.')
    routing = _resolve_source_routing(source_doc, data.get('routing_id'))
    process_bom = _process_bom_for_routing(
        source_doc,
        routing,
        process_bom_id=data.get('process_bom_id'),
    )
    return source_doc, routing, process_bom


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
    target.other_cost_amount = source.other_cost_amount
    src_code = source.tech_doc.product_code
    copied = f'Sao chép từ {src_code} / {source.version_label}'
    target.notes = (source.notes or '').strip() or copied
    target.save(update_fields=[
        'overhead_pct', 'overhead_amount', 'other_cost_amount', 'notes', 'updated_at',
    ])
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
    include_bom: bool | None = None,
    include_ob: bool | None = None,
) -> PasteResult:
    if source_doc.pk == target_doc.pk:
        raise TechDocCopyError('Chọn hồ sơ thiết kế khác — không dán đè lên chính hồ sơ đang copy.')

    want_bom = source_bom is not None if include_bom is None else include_bom
    want_ob = source_routing is not None if include_ob is None else include_ob
    if want_bom and source_bom is None:
        raise TechDocCopyError('Không có BOM để dán.')
    if want_ob and source_routing is None:
        raise TechDocCopyError('Không có OB để dán.')
    if not want_bom and not want_ob:
        raise TechDocCopyError('Không có BOM hoặc OB để dán.')

    result = PasteResult(target_doc=target_doc, bom=target_bom, routing=target_routing)
    line_map: dict[int, SxRoutingLine] = {}

    paste_bom = want_bom
    if paste_bom:
        if target_bom is None:
            target_bom = get_working_bom(target_doc)
        if (
            target_bom is not None
            and not source_bom.lines.exists()
            and target_bom.lines.exists()
        ):
            paste_bom = False
            result.bom = target_bom
        else:
            if target_bom is None:
                target_bom = create_bom_version(target_doc, user=user)
                result.bom_new_version = True
            elif is_bom_locked(target_bom):
                target_bom = create_bom_version(target_doc, user=user)
                result.bom_new_version = True
            result.n_bom_lines = _copy_bom_lines(source_bom, target_bom)
            result.bom = target_bom
            result.bom_pasted = True

    paste_ob = want_ob
    if paste_ob:
        if target_routing is None:
            target_routing = resolve_doc_routing(target_doc, bom=result.bom or target_bom)
        if (
            target_routing is not None
            and not source_routing.lines.exists()
            and target_routing.lines.exists()
        ):
            paste_ob = False
            result.routing = target_routing
        else:
            try:
                if target_routing is None:
                    target_routing = create_blank_routing(tech_doc=target_doc, user=user)
                    result.routing_new_version = True
                elif is_routing_locked(target_routing):
                    target_routing = create_blank_routing(tech_doc=target_doc, user=user)
                    result.routing_new_version = True
                else:
                    if result.bom is not None:
                        result.bom.process_steps.filter(routing_line__routing=target_routing).update(
                            routing_line=None,
                        )
                    target_routing.lines.all().delete()
                    _reset_routing_approval(target_routing)
            except IeOpsError as exc:
                raise TechDocCopyError(str(exc)) from exc
            line_map = _copy_routing_lines(source_routing, target_routing)
            result.n_ob_lines = len(line_map)
            result.routing = target_routing
            result.ob_pasted = True

    if not paste_bom and not paste_ob:
        if want_bom and not want_ob:
            raise TechDocCopyError('Bản copy không có NPL — không dán đè lên hồ sơ đang có dữ liệu.')
        if want_ob and not want_bom:
            raise TechDocCopyError('Bản copy không có công đoạn — không dán đè lên hồ sơ đang có dữ liệu.')
        raise TechDocCopyError(
            'Bản copy không có NPL/công đoạn — không dán đè lên hồ sơ đang có dữ liệu.'
        )

    target_bom = result.bom
    target_routing = result.routing
    copied_ob = paste_ob and target_routing is not None
    bom_writable = target_bom is not None and not is_bom_locked(target_bom)
    if copied_ob and bom_writable and target_bom.routing_id != target_routing.pk:
        target_bom.routing = target_routing
        target_bom.save(update_fields=['routing', 'updated_at'])

    if copied_ob and bom_writable:
        target_bom.process_steps.all().delete()
        if source_bom is not None:
            _copy_process_steps(
                source_bom,
                target_bom,
                line_map=line_map,
                target_routing=target_routing,
            )
        else:
            _rebuild_process_steps_from_routing(target_bom, target_routing)

    return result


def paste_bom(
    *,
    source_doc: ProductTechDoc,
    source_bom: BomVersion,
    target_doc: ProductTechDoc,
    target_bom: BomVersion | None = None,
    user=None,
) -> PasteResult:
    return paste_bom_and_ob(
        source_doc=source_doc,
        source_bom=source_bom,
        source_routing=None,
        target_doc=target_doc,
        target_bom=target_bom,
        user=user,
        include_bom=True,
        include_ob=False,
    )


def paste_ob(
    *,
    source_doc: ProductTechDoc,
    source_routing: SxRouting,
    target_doc: ProductTechDoc,
    target_bom: BomVersion | None = None,
    target_routing: SxRouting | None = None,
    process_bom: BomVersion | None = None,
    user=None,
) -> PasteResult:
    return paste_bom_and_ob(
        source_doc=source_doc,
        source_bom=process_bom,
        source_routing=source_routing,
        target_doc=target_doc,
        target_bom=target_bom,
        target_routing=target_routing,
        user=user,
        include_bom=False,
        include_ob=True,
    )
