"""Nghiệp vụ IE: áp routing vào BOM, duyệt bấm giờ cập nhật SMV routing.

Kiểm soát theo 00_HUONG_DAN:
1. SMV phải > 0 khi duyệt/phát hành
2. Routing đã gắn lệnh SX bị khóa — phải tạo REV mới
3. |SMV_VARIANCE_PCT| > 15% bắt buộc giải trình trước khi duyệt
4. Luồng duyệt OP / routing (Approver)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Avg, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from san_xuat.ie_models import (
    SxMachine,
    SxOperation,
    SxOperationGroup,
    SxRouting,
    SxRoutingLine,
    SxTimeStudy,
)
from san_xuat.models import BomVersion, ProcessStep
from san_xuat.services.capacity_from_hrm import map_ie_center_to_hr
from san_xuat.services.process_catalog import ensure_process_name


class IeOpsError(Exception):
    pass


VARIANCE_LIMIT_PCT = Decimal('15')


def _q(value: Decimal, places: str = '0.0001') -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _match_op_codes(op_code: str) -> Q:
    """Khớp OP_CODE đầy đủ hoặc dạng rút gọn (SEW-1005 ↔ SEW-NEK-1005)."""
    op_code = (op_code or '').strip()
    if not op_code:
        return Q(pk__in=[])
    q = Q(op_code=op_code) | Q(op_code__iendswith=op_code)
    parts = op_code.split('-')
    if parts:
        q |= Q(op_code__iendswith=f'-{parts[-1]}')
    return q


def resolve_operation(op_code: str, op_rev: str | None = None) -> SxOperation | None:
    """Tìm công đoạn thư viện — ưu tiên khớp đúng, rồi mã rút gọn."""
    op_code = (op_code or '').strip()
    if not op_code:
        return None
    rev = (op_rev or '').strip() or None
    if rev:
        hit = SxOperation.objects.filter(op_code=op_code, op_rev=rev).first()
        if hit:
            return hit
    hit = SxOperation.objects.filter(op_code=op_code).order_by('-op_rev').first()
    if hit:
        return hit
    qs = SxOperation.objects.filter(_match_op_codes(op_code))
    if rev:
        hit = qs.filter(op_rev=rev).order_by('op_code').first()
        if hit:
            return hit
    return qs.order_by('-op_rev', 'op_code').first()


def link_time_studies_to_operations(*, only_unlinked: bool = True) -> dict:
    """Gắn FK operation cho time study (mã rút gọn → mã đầy đủ)."""
    qs = SxTimeStudy.objects.all()
    if only_unlinked:
        qs = qs.filter(operation__isnull=True)
    linked = skipped = 0
    for study in qs.iterator():
        op = resolve_operation(study.op_code, study.op_rev)
        if not op:
            skipped += 1
            continue
        study.operation = op
        study.save(update_fields=['operation'])
        linked += 1
    return {'linked': linked, 'skipped': skipped, 'total': linked + skipped}


def assert_smv_positive(smv, *, label: str = 'SMV') -> Decimal:
    try:
        value = Decimal(str(smv)) if smv is not None else Decimal('0')
    except Exception as exc:
        raise IeOpsError(f'{label} không hợp lệ.') from exc
    if value <= 0:
        raise IeOpsError(f'{label} phải > 0 (theo 00_HUONG_DAN — kiểm soát phát hành).')
    return value


def is_routing_locked(routing: SxRouting) -> bool:
    """Routing đã gắn lệnh sản xuất thì khóa sửa đè (nguyên tắc 5)."""
    if routing is None:
        return False
    from san_xuat.hub_models import SxProductionOrder

    return SxProductionOrder.objects.filter(routing_id=routing.pk).exists()


def assert_routing_editable(routing: SxRouting) -> None:
    if is_routing_locked(routing):
        raise IeOpsError(
            f'Routing {routing.routing_id} đã gắn lệnh SX — không được sửa đè. '
            f'Hãy tạo phiên bản (REV) mới.'
        )


def require_variance_explanation(variance_pct, explanation: str, *, label: str = '') -> None:
    try:
        pct = Decimal(str(variance_pct or 0))
    except Exception:
        pct = Decimal('0')
    if abs(pct) <= VARIANCE_LIMIT_PCT:
        return
    if not (explanation or '').strip():
        prefix = f'{label}: ' if label else ''
        raise IeOpsError(
            f'{prefix}|Chênh lệch SMV| = {pct}% > {VARIANCE_LIMIT_PCT}% — '
            f'cần giải trình trước khi duyệt (00_HUONG_DAN).'
        )


@dataclass
class ApplyRoutingResult:
    steps_created: int = 0
    routing_id: str = ''
    linked_only: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class ApproveTimeStudyResult:
    study_id: str = ''
    new_smv: Decimal = Decimal('0')
    sample_count: int = 0
    routing_lines_updated: int = 0
    library_updated: bool = False
    warnings: list[str] = field(default_factory=list)


def _next_routing_rev(style_code: str, preferred: str = 'R01') -> str:
    preferred = (preferred or 'R01').strip().upper() or 'R01'
    if not preferred.startswith('R'):
        preferred = f'R{preferred}'
    existing = set(
        SxRouting.objects.filter(style_code=style_code).values_list('routing_rev', flat=True)
    )
    if preferred not in existing:
        return preferred
    for i in range(1, 100):
        cand = f'R{i:02d}'
        if cand not in existing:
            return cand
    raise IeOpsError(f'Không còn phiên bản routing trống cho {style_code}.')


def _parse_routing_input(raw: str, *, default_style: str = '') -> tuple[str, str, str]:
    """Trả (style_code, routing_rev, routing_id) từ chuỗi người dùng gõ."""
    text = (raw or '').strip().upper().replace(' ', '')
    default_style = (default_style or '').strip().upper()
    if not text and not default_style:
        raise IeOpsError('Nhập mã hàng hoặc mã routing.')

    if text:
        parts = text.rsplit('-', 1)
        if len(parts) == 2 and parts[1].startswith('R') and parts[1][1:].isdigit():
            style_code = parts[0] or default_style
            routing_rev = parts[1]
            if not style_code:
                raise IeOpsError('Thiếu mã hàng trong mã routing.')
            return style_code, routing_rev, f'{style_code}-{routing_rev}'
        style_code = text
        routing_rev = 'R01'
        return style_code, routing_rev, f'{style_code}-{routing_rev}'

    style_code = default_style
    routing_rev = 'R01'
    return style_code, routing_rev, f'{style_code}-{routing_rev}'


@transaction.atomic
def create_blank_routing(
    *,
    style_code: str = '',
    routing_id: str = '',
    style_name: str = '',
    product_family: str = '',
    tech_doc=None,
    user=None,
) -> SxRouting:
    """Tạo routing trống (không cần Excel) để gắn BOM / nhập công đoạn tay."""
    default_style = ''
    if tech_doc is not None:
        default_style = (getattr(tech_doc, 'product_code', None) or '').strip()
    seed = (routing_id or style_code or default_style).strip()
    style, rev, rid = _parse_routing_input(seed, default_style=default_style)
    rev = _next_routing_rev(style, preferred=rev)
    rid = f'{style}-{rev}'

    if SxRouting.objects.filter(routing_id=rid).exists():
        raise IeOpsError(f'Routing {rid} đã tồn tại.')

    if not style_name and tech_doc is not None:
        style_name = (getattr(tech_doc, 'product_name', None) or '')[:255]

    return SxRouting.objects.create(
        routing_id=rid,
        style_code=style,
        style_name=(style_name or '')[:255],
        product_family=(product_family or '')[:150],
        routing_rev=rev,
        tech_doc=tech_doc,
        is_active=True,
        approval_status=SxRouting.APPROVAL_DRAFT,
        notes='Tạo tay (không import Excel)',
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )


def _next_op_rev(op_code: str, preferred: str = 'R01') -> str:
    preferred = (preferred or 'R01').strip().upper() or 'R01'
    if not preferred.startswith('R'):
        preferred = f'R{preferred}'
    existing = set(
        SxOperation.objects.filter(op_code=op_code).values_list('op_rev', flat=True)
    )
    if preferred not in existing:
        return preferred
    for i in range(1, 100):
        cand = f'R{i:02d}'
        if cand not in existing:
            return cand
    raise IeOpsError(f'Không còn phiên bản trống cho công đoạn {op_code}.')


@transaction.atomic
def create_blank_operation(
    *,
    op_code: str,
    name_vi: str,
    group: SxOperationGroup | None = None,
    group_code: str = '',
    op_rev: str = 'R01',
    base_smv_min: Decimal | None = None,
    machine_code: str = '',
    process_stage_label: str = '',
) -> SxOperation:
    """Tạo công đoạn chuẩn tay (không cần Excel)."""
    op_code = (op_code or '').strip().upper()
    name_vi = (name_vi or '').strip()
    if not op_code:
        raise IeOpsError('Nhập mã công đoạn.')
    if not name_vi:
        raise IeOpsError('Nhập tên công đoạn.')

    if group is None:
        code = (group_code or '').strip() or 'MANUAL'
        group, _ = SxOperationGroup.objects.get_or_create(
            code=code,
            defaults={
                'name': 'Tạo tay' if code == 'MANUAL' else code,
                'notes': 'Nhóm mặc định cho công đoạn tạo tay',
            },
        )

    rev = _next_op_rev(op_code, preferred=op_rev)
    smv = base_smv_min if base_smv_min is not None else Decimal('0')
    if smv < 0:
        raise IeOpsError('SMV không được âm.')

    ensure_process_name(name_vi)

    return SxOperation.objects.create(
        group=group,
        op_code=op_code,
        op_rev=rev,
        name_vi=name_vi[:200],
        process_stage_label=(process_stage_label or group.process_stage_label or '')[:100],
        machine_code=(machine_code or '')[:40],
        base_smv_min=smv,
        status=SxOperation.STATUS_DRAFT,
        notes='Tạo tay (không import Excel)',
        revision_reason='Tạo tay',
    )


@transaction.atomic
def create_operation_group(
    *,
    code: str,
    name: str,
    process_stage_label: str = '',
    product_part: str = '',
) -> SxOperationGroup:
    """Tạo nhóm công đoạn tay."""
    code = (code or '').strip().upper()
    name = (name or '').strip()
    if not code:
        raise IeOpsError('Nhập mã nhóm.')
    if not name:
        raise IeOpsError('Nhập tên nhóm.')
    if SxOperationGroup.objects.filter(code=code).exists():
        raise IeOpsError(f'Nhóm {code} đã tồn tại.')
    return SxOperationGroup.objects.create(
        code=code,
        name=name[:150],
        process_stage_label=(process_stage_label or '')[:100],
        product_part=(product_part or '')[:120],
        notes='Tạo tay (không import Excel)',
    )


def update_operation_group(
    *,
    group: SxOperationGroup,
    name: str,
    process_stage_label: str = '',
    product_part: str = '',
) -> SxOperationGroup:
    name = (name or '').strip()
    if group is None:
        raise IeOpsError('Thiếu nhóm công đoạn.')
    if not name:
        raise IeOpsError('Nhập tên nhóm.')
    group.name = name[:150]
    group.process_stage_label = (process_stage_label or '')[:100]
    group.product_part = (product_part or '')[:120]
    group.save(update_fields=['name', 'process_stage_label', 'product_part', 'updated_at'])
    return group


def delete_operation_group(*, group: SxOperationGroup) -> None:
    if group is None:
        raise IeOpsError('Thiếu nhóm công đoạn.')
    n = group.operations.count()
    if n:
        raise IeOpsError(
            f'Không xóa được nhóm {group.code}: còn {n} công đoạn. '
            f'Hãy chuyển công đoạn sang nhóm khác trước.'
        )
    try:
        group.delete()
    except ProtectedError as exc:
        raise IeOpsError(f'Không xóa được nhóm {group.code}: đang được tham chiếu.') from exc


def delete_operation(*, operation: SxOperation) -> str:
    if operation is None:
        raise IeOpsError('Thiếu công đoạn.')
    label = f'{operation.op_code}/{operation.op_rev}'
    try:
        operation.delete()
    except ProtectedError as exc:
        raise IeOpsError(f'Không xóa được {label}: đang được tham chiếu.') from exc
    return label


def update_routing_header(
    *,
    routing: SxRouting,
    style_name: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> SxRouting:
    if routing is None:
        raise IeOpsError('Thiếu routing.')
    if style_name is not None:
        routing.style_name = (style_name or '')[:255]
    if notes is not None:
        routing.notes = (notes or '')[:255]
    if is_active is not None:
        routing.is_active = bool(is_active)
    routing.save()
    return routing


def delete_routing(*, routing: SxRouting) -> str:
    if routing is None:
        raise IeOpsError('Thiếu routing.')
    assert_routing_editable(routing)
    rid = routing.routing_id
    try:
        routing.delete()
    except ProtectedError as exc:
        raise IeOpsError(f'Không xóa được {rid}: đang được tham chiếu (lệnh SX / đơn hàng).') from exc
    return rid


@transaction.atomic
def create_time_study(
    *,
    op_code: str,
    observed_cycle_sec: Decimal,
    style_code: str = '',
    op_name_vi: str = '',
    op_rev: str = 'R01',
    abnormal_sec: Decimal | None = None,
    performance_rating: Decimal | None = None,
    allowance_pct: Decimal | None = None,
    current_routing_smv: Decimal | None = None,
    study_id: str = '',
) -> SxTimeStudy:
    """Tạo quan sát bấm giờ tay."""
    from datetime import date

    op_code = (op_code or '').strip().upper()
    if not op_code:
        raise IeOpsError('Nhập mã công đoạn.')
    if observed_cycle_sec is None or observed_cycle_sec < 0:
        raise IeOpsError('Chu kỳ quan sát (giây) không hợp lệ.')

    op = resolve_operation(op_code, op_rev)
    if not op_name_vi and op:
        op_name_vi = op.name_vi
    if not op_rev and op:
        op_rev = op.op_rev

    sid = (study_id or '').strip().upper()
    if not sid:
        prefix = f'TS-{date.today():%y%m%d}'
        n = SxTimeStudy.objects.filter(study_id__startswith=prefix).count() + 1
        sid = f'{prefix}-{n:03d}'
    if SxTimeStudy.objects.filter(study_id=sid).exists():
        raise IeOpsError(f'Mã quan sát {sid} đã tồn tại.')

    study = SxTimeStudy.objects.create(
        study_id=sid,
        study_date=date.today(),
        style_code=(style_code or '')[:60],
        operation=op,
        op_code=op_code[:30],
        op_rev=(op_rev or (op.op_rev if op else 'R01'))[:10],
        op_name_vi=(op_name_vi or '')[:200],
        observed_cycle_sec=observed_cycle_sec,
        abnormal_sec=abnormal_sec if abnormal_sec is not None else Decimal('0'),
        performance_rating=performance_rating if performance_rating is not None else Decimal('1'),
        allowance_pct=allowance_pct if allowance_pct is not None else Decimal('0'),
        current_routing_smv=current_routing_smv if current_routing_smv is not None else Decimal('0'),
        notes='Tạo tay (không import Excel)',
    )
    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event

    log_ie_event(
        action=SxIeAuditLog.ACTION_CREATE,
        summary=f'Tạo time study {study.study_id}',
        object_type='SxTimeStudy',
        object_id=study.pk,
        object_repr=study.study_id,
    )
    return study


@transaction.atomic
def update_operation(
    *,
    operation: SxOperation,
    user=None,
    name_vi: str | None = None,
    name_en: str | None = None,
    group: SxOperationGroup | None = None,
    process_stage_label: str | None = None,
    product_part: str | None = None,
    method_variant: str | None = None,
    machine_code: str | None = None,
    skill_level_label: str | None = None,
    stitch_class_code: str | None = None,
    smv_source_code: str | None = None,
    base_smv_min: Decimal | None = None,
    smv_basis: str | None = None,
    qc_criteria: str | None = None,
    status: str | None = None,
    ie_owner: str | None = None,
    revision_reason: str | None = None,
    notes: str | None = None,
    work_instruction_url: str | None = None,
    video_url: str | None = None,
) -> SxOperation:
    """Cập nhật công đoạn chuẩn trên UI. Đổi SMV khi đã duyệt → về nháp."""
    if operation is None:
        raise IeOpsError('Thiếu công đoạn.')

    from san_xuat.ie_models import SxIeAuditLog, SxMachine, SxSkillLevel, SxSmvSource, SxStitchClass
    from san_xuat.services.ie_audit import log_ie_event

    changes: dict = {}
    old_smv = operation.base_smv_min

    def _set(field: str, value, *, cast=None):
        if value is None:
            return
        if cast:
            value = cast(value)
        current = getattr(operation, field)
        if current != value:
            changes[field] = {'from': str(current), 'to': str(value)}
            setattr(operation, field, value)

    if name_vi is not None:
        name = name_vi.strip()
        if not name:
            raise IeOpsError('Tên công đoạn không được trống.')
        ensure_process_name(name)
        _set('name_vi', name[:200])
    _set('name_en', None if name_en is None else name_en.strip()[:200])
    if group is not None:
        if operation.group_id != group.pk:
            changes['group'] = {'from': operation.group.code, 'to': group.code}
            operation.group = group
    _set('process_stage_label', None if process_stage_label is None else process_stage_label.strip()[:100])
    _set('product_part', None if product_part is None else product_part.strip()[:120])
    _set('method_variant', None if method_variant is None else method_variant.strip())

    if machine_code is not None:
        code = machine_code.strip()[:40]
        machine = SxMachine.objects.filter(code=code).first() if code else None
        _set('machine_code', code)
        if operation.machine_id != (machine.pk if machine else None):
            changes['machine'] = {
                'from': str(operation.machine_id or ''),
                'to': str(machine.pk if machine else ''),
            }
            operation.machine = machine

    if skill_level_label is not None:
        label = skill_level_label.strip()[:60]
        skill = None
        if label:
            skill = (
                SxSkillLevel.objects.filter(name=label).first()
                or SxSkillLevel.objects.filter(code=label).first()
            )
        _set('skill_level_label', label)
        if operation.skill_level_id != (skill.pk if skill else None):
            changes['skill_level'] = {
                'from': str(operation.skill_level_id or ''),
                'to': str(skill.pk if skill else ''),
            }
            operation.skill_level = skill

    if stitch_class_code is not None:
        code = stitch_class_code.strip()[:40]
        stitch = SxStitchClass.objects.filter(code=code).first() if code else None
        if operation.stitch_class_id != (stitch.pk if stitch else None):
            changes['stitch_class'] = {
                'from': str(operation.stitch_class_id or ''),
                'to': str(stitch.pk if stitch else ''),
            }
            operation.stitch_class = stitch

    if smv_source_code is not None:
        code = smv_source_code.strip()[:40]
        src = None
        if code:
            src = (
                SxSmvSource.objects.filter(code=code).first()
                or SxSmvSource.objects.filter(name=code).first()
            )
        if operation.smv_source_id != (src.pk if src else None):
            changes['smv_source'] = {
                'from': str(operation.smv_source_id or ''),
                'to': str(src.pk if src else ''),
            }
            operation.smv_source = src

    if base_smv_min is not None:
        if base_smv_min < 0:
            raise IeOpsError('SMV không được âm.')
        _set('base_smv_min', base_smv_min)
    _set('smv_basis', None if smv_basis is None else smv_basis.strip()[:60])
    _set('qc_criteria', None if qc_criteria is None else qc_criteria.strip())
    _set('ie_owner', None if ie_owner is None else ie_owner.strip()[:120])
    _set('revision_reason', None if revision_reason is None else revision_reason.strip()[:255])
    _set('notes', None if notes is None else notes.strip()[:255])
    _set('work_instruction_url', None if work_instruction_url is None else work_instruction_url.strip()[:500])
    _set('video_url', None if video_url is None else video_url.strip()[:500])

    if status is not None:
        allowed = {c[0] for c in SxOperation.STATUS_CHOICES}
        if status not in allowed:
            raise IeOpsError('Trạng thái không hợp lệ.')
        if status == SxOperation.STATUS_APPROVED and operation.status != SxOperation.STATUS_APPROVED:
            raise IeOpsError('Dùng nút Duyệt để phê duyệt công đoạn.')
        _set('status', status)

    smv_changed = 'base_smv_min' in changes
    if smv_changed and operation.status == SxOperation.STATUS_APPROVED:
        operation.status = SxOperation.STATUS_DRAFT
        operation.approved_by = ''
        operation.approved_at = None
        changes['status'] = {
            'from': SxOperation.STATUS_APPROVED,
            'to': SxOperation.STATUS_DRAFT,
            'reason': 'smv_changed',
        }

    if not changes:
        return operation

    operation.save()
    action = SxIeAuditLog.ACTION_SMV_CHANGE if smv_changed else SxIeAuditLog.ACTION_UPDATE
    log_ie_event(
        action=action,
        summary=(
            f'Đổi SMV {operation.op_code}/{operation.op_rev}: {old_smv} → {operation.base_smv_min}'
            if smv_changed
            else f'Cập nhật {operation.op_code}/{operation.op_rev}'
        ),
        object_type='SxOperation',
        object_id=operation.pk,
        object_repr=f'{operation.op_code}/{operation.op_rev}',
        changes=changes,
        user=user,
    )
    return operation


def _routing_line_group(line: SxRoutingLine) -> tuple[str, str]:
    """Mã + tên nhóm công đoạn của một dòng routing."""
    op = line.operation
    if op is not None and op.group_id:
        grp = op.group
        return (grp.code or '').strip(), (grp.name or grp.code or '').strip()
    code = (line.group_code or '').strip()
    if code:
        grp = SxOperationGroup.objects.filter(code__iexact=code).first()
        if grp:
            return (grp.code or '').strip(), (grp.name or grp.code or '').strip()
        return code, code
    name = (line.op_name_vi or line.op_code or '').strip()
    return name, name


@transaction.atomic
def apply_routing_to_bom(
    *,
    bom: BomVersion,
    routing: SxRouting,
    replace: bool = True,
    by_group: bool = False,
) -> ApplyRoutingResult:
    """Gắn routing vào BOM và đồng bộ ProcessStep từ dòng routing.

    - std_time_minutes = tổng SMV công đoạn (qty × SMV áp dụng)
    - norm_per_hour = 60 / SMV áp dụng (cái/giờ trên 1 đơn vị cơ sở)
    - Routing trống: chỉ gắn BOM, giữ nguyên công đoạn hiện có (nhập tay).
    - Phát hành: SMV áp dụng phải > 0 trên mọi dòng có công đoạn.
    - by_group=True: gộp thành một bước BOM theo nhóm công đoạn (không tạo ~50 CĐ).
    """
    if bom is None:
        raise IeOpsError('Thiếu BOM.')
    if routing is None:
        raise IeOpsError('Thiếu routing.')

    lines = list(
        routing.lines.select_related('operation__group', 'work_center').order_by('seq_no')
    )
    result = ApplyRoutingResult(routing_id=routing.routing_id)
    bom.routing = routing
    bom.save(update_fields=['routing', 'updated_at'])

    if not lines:
        result.linked_only = True
        result.warnings.append(
            f'Routing {routing.routing_id} chưa có dòng — đã gắn vào BOM, giữ công đoạn hiện có (có thể thêm tay).'
        )
        return result

    if replace:
        zero_smv = [ln.op_code for ln in lines if (ln.applied_unit_smv or Decimal('0')) <= 0]
        if zero_smv:
            raise IeOpsError(
                f'Không áp routing: còn {len(zero_smv)} dòng SMV ≤ 0 '
                f'({", ".join(zero_smv[:5])}{"…" if len(zero_smv) > 5 else ""}).'
            )
        bom.process_steps.all().delete()

    if by_group:
        buckets: dict[str, list[SxRoutingLine]] = {}
        order: list[str] = []
        for line in lines:
            code, name = _routing_line_group(line)
            if not name:
                result.warnings.append(f'Bỏ qua seq {line.seq_no}: thiếu nhóm/tên công đoạn.')
                continue
            key = (code or name).casefold()
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(line)

        seq = 0
        for key in order:
            glines = buckets[key]
            _code, name = _routing_line_group(glines[0])
            ensure_process_name(name)
            seq += 10
            applied_sum = sum(
                (ln.applied_unit_smv or Decimal('0')) * (ln.qty_per_garment or Decimal('1'))
                for ln in glines
            )
            total_smv = sum((ln.total_operation_smv or Decimal('0')) for ln in glines)
            if applied_sum > 0:
                norm = _q(Decimal('60') / applied_sum, '0.01')
                if norm < Decimal('0.01'):
                    norm = Decimal('0.01')
            else:
                norm = Decimal('0.01')
                result.warnings.append(f'{name}: SMV = 0 → đặt định mức tối thiểu 0.01 cái/giờ.')

            wc = None
            for ln in glines:
                wc = map_ie_center_to_hr(ln.work_center)
                if wc:
                    break
            if wc is None:
                grp = SxOperationGroup.objects.filter(code__iexact=_code).select_related(
                    'default_work_center'
                ).first() if _code else None
                if grp:
                    wc = map_ie_center_to_hr(grp.default_work_center)

            ProcessStep.objects.create(
                bom=bom,
                sequence=seq,
                process_name=name[:120],
                operation=None,
                op_code=(_code or '')[:30],
                routing_line=glines[0],
                norm_per_hour=norm,
                std_time_minutes=_q(total_smv, '0.01'),
                work_center=wc,
                cost_per_hour=Decimal('0'),
                piece_rate=Decimal('0'),
                notes=f'IE nhóm {name} ({len(glines)} CĐ)'[:255],
            )
            result.steps_created += 1
        return result

    for line in lines:
        name = (line.op_name_vi or line.op_code or '').strip()
        if not name:
            result.warnings.append(f'Bỏ qua seq {line.seq_no}: thiếu tên công đoạn.')
            continue
        ensure_process_name(name)

        applied = line.applied_unit_smv or Decimal('0')
        total_smv = line.total_operation_smv or Decimal('0')
        if applied > 0:
            norm = _q(Decimal('60') / applied, '0.01')
            if norm < Decimal('0.01'):
                norm = Decimal('0.01')
        else:
            norm = Decimal('0.01')
            result.warnings.append(f'{line.op_code}: SMV = 0 → đặt định mức tối thiểu 0.01 cái/giờ.')

        ProcessStep.objects.create(
            bom=bom,
            sequence=line.seq_no or 10,
            process_name=name[:120],
            operation=line.operation,
            op_code=line.op_code or '',
            routing_line=line,
            norm_per_hour=norm,
            std_time_minutes=_q(total_smv, '0.01'),
            work_center=map_ie_center_to_hr(line.work_center),
            cost_per_hour=Decimal('0'),
            piece_rate=Decimal('0'),
            notes=f'IE {line.op_code}/{line.op_rev}'[:255],
        )
        result.steps_created += 1

    return result


@transaction.atomic
def approve_operation(*, operation: SxOperation, user=None) -> SxOperation:
    """Duyệt công đoạn chuẩn (Approver) — bắt buộc BASE_SMV_MIN > 0."""
    if operation is None:
        raise IeOpsError('Thiếu công đoạn.')
    assert_smv_positive(operation.base_smv_min, label=f'{operation.op_code} BASE_SMV_MIN')
    operation.status = SxOperation.STATUS_APPROVED
    operation.approved_by = (
        getattr(user, 'get_full_name', lambda: '')()
        or getattr(user, 'username', '')
        or operation.approved_by
        or 'Approver'
    )[:120]
    operation.approved_at = timezone.now()
    operation.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event

    log_ie_event(
        action=SxIeAuditLog.ACTION_APPROVE,
        summary=f'Duyệt OP {operation.op_code}/{operation.op_rev} SMV={operation.base_smv_min}',
        object_type='SxOperation',
        object_id=operation.pk,
        object_repr=f'{operation.op_code}/{operation.op_rev}',
        changes={'status': {'to': operation.status}, 'smv': str(operation.base_smv_min)},
        user=user,
    )
    return operation


@transaction.atomic
def approve_routing(*, routing: SxRouting, user=None) -> SxRouting:
    """Duyệt routing phát hành — SMV > 0 + giải trình lệch > 15%."""
    if routing is None:
        raise IeOpsError('Thiếu routing.')
    lines = list(routing.lines.order_by('seq_no'))
    if not lines:
        raise IeOpsError(f'Routing {routing.routing_id} chưa có công đoạn.')
    for line in lines:
        assert_smv_positive(line.applied_unit_smv, label=f'{line.op_code} APPLIED_UNIT_SMV')
        require_variance_explanation(
            line.smv_variance_pct,
            line.variance_explanation,
            label=f'{line.op_code}#{line.seq_no}',
        )
    routing.approval_status = SxRouting.APPROVAL_APPROVED
    routing.approved_by = (
        getattr(user, 'get_full_name', lambda: '')()
        or getattr(user, 'username', '')
        or routing.approved_by
        or 'Approver'
    )[:120]
    routing.approved_at = timezone.now()
    if not routing.effective_from:
        routing.effective_from = timezone.localdate()
    routing.is_active = True
    routing.save(update_fields=[
        'approval_status', 'approved_by', 'approved_at', 'effective_from', 'is_active', 'updated_at',
    ])
    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event

    log_ie_event(
        action=SxIeAuditLog.ACTION_APPROVE,
        summary=f'Duyệt routing {routing.routing_id} ({len(lines)} dòng)',
        object_type='SxRouting',
        object_id=routing.pk,
        object_repr=routing.routing_id,
        user=user,
    )
    return routing


@transaction.atomic
def reject_routing(*, routing: SxRouting, user=None) -> SxRouting:
    if routing is None:
        raise IeOpsError('Thiếu routing.')
    assert_routing_editable(routing)
    routing.approval_status = SxRouting.APPROVAL_REJECTED
    routing.save(update_fields=['approval_status', 'updated_at'])
    return routing


@transaction.atomic
def clone_routing_revision(*, routing: SxRouting, user=None) -> SxRouting:
    """Tạo REV mới copy toàn bộ dòng — dùng khi routing đã khóa / đã phát hành."""
    if routing is None:
        raise IeOpsError('Thiếu routing.')
    new_rev = _next_routing_rev(routing.style_code, preferred='R01')
    # Prefer next after current
    try:
        cur_n = int((routing.routing_rev or 'R01').lstrip('R') or '1')
        preferred = f'R{cur_n + 1:02d}'
        new_rev = _next_routing_rev(routing.style_code, preferred=preferred)
    except ValueError:
        pass
    rid = f'{routing.style_code}-{new_rev}'
    clone = SxRouting.objects.create(
        routing_id=rid,
        style_code=routing.style_code,
        style_name=routing.style_name,
        product_family=routing.product_family,
        routing_rev=new_rev,
        tech_doc=routing.tech_doc,
        effective_from=None,
        is_active=True,
        approval_status=SxRouting.APPROVAL_DRAFT,
        ie_owner=routing.ie_owner,
        notes=f'Clone từ {routing.routing_id}'[:255],
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    for line in routing.lines.order_by('seq_no'):
        SxRoutingLine.objects.create(
            routing=clone,
            seq_no=line.seq_no,
            operation=line.operation,
            op_code=line.op_code,
            op_rev=line.op_rev,
            op_name_vi=line.op_name_vi,
            group_code=line.group_code,
            qty_per_garment=line.qty_per_garment,
            library_unit_smv=line.library_unit_smv,
            applied_unit_smv=line.applied_unit_smv,
            machine=line.machine,
            machine_code=line.machine_code,
            work_center=line.work_center,
            work_center_code=line.work_center_code,
            predecessor_seq=line.predecessor_seq,
            parallel_group=line.parallel_group,
            bundle_size=line.bundle_size,
            skill_level_label=line.skill_level_label,
            critical_qc=line.critical_qc,
            target_efficiency=line.target_efficiency,
            notes=line.notes,
            variance_explanation=line.variance_explanation,
        )
    return clone


@transaction.atomic
def save_routing_line_explanations(*, routing: SxRouting, explanations: dict[int, str]) -> int:
    """Lưu giải trình lệch SMV theo pk dòng. Routing khóa thì không cho sửa."""
    assert_routing_editable(routing)
    updated = 0
    for pk, text in explanations.items():
        line = routing.lines.filter(pk=pk).first()
        if not line:
            continue
        line.variance_explanation = (text or '')[:500]
        line.save(update_fields=['variance_explanation'])
        updated += 1
    if routing.approval_status == SxRouting.APPROVAL_APPROVED:
        routing.approval_status = SxRouting.APPROVAL_PENDING
        routing.save(update_fields=['approval_status', 'updated_at'])
    return updated


def _mark_routing_pending(routing: SxRouting) -> None:
    if routing.approval_status == SxRouting.APPROVAL_APPROVED:
        routing.approval_status = SxRouting.APPROVAL_PENDING
        routing.approved_by = ''
        routing.approved_at = None
        routing.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'updated_at'])


@transaction.atomic
def upsert_routing_line(
    *,
    routing: SxRouting,
    line_pk: int | None = None,
    seq_no: int | None = None,
    op_code: str = '',
    op_rev: str = 'R01',
    op_name_vi: str = '',
    group_code: str = '',
    qty_per_garment: Decimal | None = None,
    applied_unit_smv: Decimal | None = None,
    library_unit_smv: Decimal | None = None,
    machine_code: str = '',
    work_center_code: str = '',
    variance_explanation: str = '',
    notes: str = '',
) -> SxRoutingLine:
    """Thêm hoặc sửa một dòng routing (tay)."""
    assert_routing_editable(routing)
    op_code = (op_code or '').strip().upper()
    if not op_code:
        raise IeOpsError('Nhập mã công đoạn.')
    op_rev = (op_rev or 'R01').strip() or 'R01'
    name = (op_name_vi or '').strip()
    op = resolve_operation(op_code, op_rev)
    if not name and op:
        name = op.name_vi
    if not name:
        raise IeOpsError('Nhập tên công đoạn.')

    qty = qty_per_garment if qty_per_garment is not None else Decimal('1')
    applied = applied_unit_smv if applied_unit_smv is not None else Decimal('0')
    library = library_unit_smv
    if library is None:
        library = op.base_smv_min if op else Decimal('0')
    if applied < 0 or qty < 0 or (library or 0) < 0:
        raise IeOpsError('SL/SMV không được âm.')

    machine = SxMachine.objects.filter(code=(machine_code or '').strip()).first() if machine_code else None
    from san_xuat.services.capacity_from_hrm import resolve_work_center_code

    wc_code_raw = (work_center_code or '').strip()
    if not wc_code_raw and group_code:
        from san_xuat.ie_models import SxOperationGroup
        grp = SxOperationGroup.objects.filter(code=(group_code or '').strip()).select_related(
            'default_work_center'
        ).first()
        if grp and (grp.default_work_center_code or grp.default_work_center_id):
            wc_code_raw = grp.default_work_center_code or (
                grp.default_work_center.code if grp.default_work_center_id else ''
            )
    if not wc_code_raw and op and op.group_id:
        grp = op.group
        if grp and (grp.default_work_center_code or grp.default_work_center_id):
            wc_code_raw = grp.default_work_center_code or (
                grp.default_work_center.code if grp.default_work_center_id else ''
            )
    wc = resolve_work_center_code(wc_code_raw, name_hint=f'{group_code} {name}')

    line = None
    old_smv = None
    if line_pk:
        line = routing.lines.filter(pk=line_pk).first()
        if line is None:
            raise IeOpsError('Không tìm thấy dòng routing.')
        old_smv = line.applied_unit_smv
    if seq_no is None:
        last = routing.lines.order_by('-seq_no').values_list('seq_no', flat=True).first() or 0
        seq_no = int(last) + 10
    else:
        seq_no = int(seq_no)
        conflict_qs = routing.lines.filter(seq_no=seq_no)
        if line is not None:
            conflict_qs = conflict_qs.exclude(pk=line.pk)
        if conflict_qs.exists():
            raise IeOpsError(f'SEQ {seq_no} đã tồn tại trên routing này.')

    ensure_process_name(name)
    if line is None:
        line = SxRoutingLine(routing=routing)

    line.seq_no = seq_no
    line.operation = op
    line.op_code = op_code[:30]
    line.op_rev = op_rev[:10]
    line.op_name_vi = name[:200]
    line.group_code = (group_code or (op.group.code if op else ''))[:30]
    line.qty_per_garment = qty
    line.library_unit_smv = library or Decimal('0')
    line.applied_unit_smv = applied
    line.machine = machine
    line.machine_code = (machine_code or (machine.code if machine else ''))[:40]
    line.work_center = wc
    line.work_center_code = (wc.code if wc else wc_code_raw)[:40]
    line.notes = (notes or '')[:255]
    line.recompute()
    if abs(line.smv_variance_pct or 0) > VARIANCE_LIMIT_PCT:
        require_variance_explanation(line.smv_variance_pct, variance_explanation, label=op_code)
        line.variance_explanation = (variance_explanation or '')[:500]
    elif variance_explanation:
        line.variance_explanation = variance_explanation[:500]
    line.save()
    _mark_routing_pending(routing)
    if old_smv is not None and old_smv != line.applied_unit_smv:
        from san_xuat.ie_models import SxIeAuditLog
        from san_xuat.services.ie_audit import log_ie_event

        log_ie_event(
            action=SxIeAuditLog.ACTION_SMV_CHANGE,
            summary=(
                f'Đổi SMV dòng {routing.routing_id}#{line.seq_no} {line.op_code}: '
                f'{old_smv} → {line.applied_unit_smv}'
            ),
            object_type='SxRoutingLine',
            object_id=line.pk,
            object_repr=f'{routing.routing_id}#{line.seq_no}',
            changes={'applied_unit_smv': {'from': str(old_smv), 'to': str(line.applied_unit_smv)}},
        )
    return line


@transaction.atomic
def delete_routing_line(*, routing: SxRouting, line_pk: int) -> None:
    assert_routing_editable(routing)
    line = routing.lines.filter(pk=line_pk).first()
    if line is None:
        raise IeOpsError('Không tìm thấy dòng routing.')
    line.delete()
    _mark_routing_pending(routing)


def build_ie_dashboard() -> dict:
    """Số liệu dashboard kiểu sheet 07_DASHBOARD + dữ liệu biểu đồ."""
    from django.db.models import Avg, Count, Sum, Q as DQ

    style_rows = []
    for r in (
        SxRouting.objects.filter(is_active=True)
        .annotate(
            n_lines=Count('lines'),
            sum_smv=Sum('lines__total_operation_smv'),
            sew_smv=Sum(
                'lines__total_operation_smv',
                filter=DQ(lines__op_code__istartswith='SEW') | DQ(lines__group_code__istartswith='SEW'),
            ),
            avg_target_eff=Avg('lines__target_efficiency'),
        )
        .order_by('style_code', 'routing_rev')
    ):
        total = r.sum_smv or Decimal('0')
        sew = r.sew_smv or Decimal('0')
        style_rows.append({
            'style_code': r.style_code,
            'product_family': r.product_family or r.style_name,
            'routing_id': r.routing_id,
            'routing_rev': r.routing_rev,
            'pk': r.pk,
            'approval_status': r.approval_status,
            'operation_count': r.n_lines or 0,
            'total_smv': total,
            'sewing_smv': sew,
            'other_smv': total - sew,
            'avg_target_efficiency': r.avg_target_eff or Decimal('0'),
            'sew_share_pct': (
                _q(sew / total * Decimal('100'), '0.1') if total else Decimal('0')
            ),
        })

    high_var = list(
        SxRoutingLine.objects.filter(
            DQ(smv_variance_pct__gt=VARIANCE_LIMIT_PCT) | DQ(smv_variance_pct__lt=-VARIANCE_LIMIT_PCT)
        )
        .select_related('routing')
        .order_by('-smv_variance_pct')[:40]
    )
    pending_ops = SxOperation.objects.exclude(status=SxOperation.STATUS_APPROVED).count()
    ops_approved = SxOperation.objects.filter(status=SxOperation.STATUS_APPROVED).count()
    ops_total = SxOperation.objects.count()
    pending_routings = SxRouting.objects.exclude(approval_status=SxRouting.APPROVAL_APPROVED).count()
    routings_approved = SxRouting.objects.filter(approval_status=SxRouting.APPROVAL_APPROVED).count()
    zero_smv_lines = SxRoutingLine.objects.filter(applied_unit_smv__lte=0).count()
    ts_total = SxTimeStudy.objects.count()
    ts_linked = SxTimeStudy.objects.exclude(operation_id=None).count()
    ts_approved = SxTimeStudy.objects.filter(approval_status=SxTimeStudy.APPROVAL_APPROVED).count()
    ts_pending = SxTimeStudy.objects.filter(approval_status=SxTimeStudy.APPROVAL_PENDING).count()
    high_var_count = SxRoutingLine.objects.filter(
        DQ(smv_variance_pct__gt=VARIANCE_LIMIT_PCT) | DQ(smv_variance_pct__lt=-VARIANCE_LIMIT_PCT)
    ).count()
    max_smv = max((float(r['total_smv'] or 0) for r in style_rows), default=0) or 1
    for r in style_rows:
        r['smv_bar_pct'] = round(float(r['total_smv'] or 0) / max_smv * 100, 1)
        r['sew_bar_pct'] = round(float(r['sewing_smv'] or 0) / max_smv * 100, 1)
        r['other_bar_pct'] = max(0.0, round(r['smv_bar_pct'] - r['sew_bar_pct'], 1))

    chart_style_labels = [r['style_code'] for r in style_rows]
    chart_total_smv = [float(r['total_smv'] or 0) for r in style_rows]
    chart_sew_smv = [float(r['sewing_smv'] or 0) for r in style_rows]
    chart_other_smv = [float(r['other_smv'] or 0) for r in style_rows]

    return {
        'style_rows': style_rows,
        'high_var_lines': high_var,
        'pending_ops': pending_ops,
        'ops_approved': ops_approved,
        'ops_approval_pct': round(ops_approved / ops_total * 100, 1) if ops_total else 0,
        'pending_routings': pending_routings,
        'routings_approved': routings_approved,
        'zero_smv_lines': zero_smv_lines,
        'high_var_count': high_var_count,
        'groups': SxOperationGroup.objects.count(),
        'operations': ops_total,
        'routings': SxRouting.objects.count(),
        'routing_lines': SxRoutingLine.objects.count(),
        'time_studies': ts_total,
        'time_studies_linked': ts_linked,
        'time_studies_unlinked': ts_total - ts_linked,
        'time_studies_approved': ts_approved,
        'time_studies_pending': ts_pending,
        'ts_link_pct': round(ts_linked / ts_total * 100, 1) if ts_total else 0,
        'styles': SxRouting.objects.values('style_code').distinct().count(),
        'variance_limit': VARIANCE_LIMIT_PCT,
        'max_smv': max_smv,
        'total_smv_all': sum((r['total_smv'] for r in style_rows), Decimal('0')),
        'total_sew_smv_all': sum((r['sewing_smv'] for r in style_rows), Decimal('0')),
        'chart_style_labels': chart_style_labels,
        'chart_total_smv': chart_total_smv,
        'chart_sew_smv': chart_sew_smv,
        'chart_other_smv': chart_other_smv,
        'chart_op_status': [ops_approved, pending_ops],
        'chart_routing_status': [routings_approved, pending_routings],
        'chart_ts_status': [ts_approved, ts_pending, max(0, ts_total - ts_approved - ts_pending)],
    }


@transaction.atomic
def approve_time_study(
    *,
    study: SxTimeStudy,
    update_library: bool = False,
    update_routing: bool = True,
    variance_explanation: str = '',
    user=None,
) -> ApproveTimeStudyResult:
    """Duyệt một quan sát bấm giờ và (tuỳ chọn) cập nhật SMV routing / thư viện.

    SMV mới = trung bình các quan sát ĐÃ DUYỆT cùng (style_code, op_code) có SMV > 0.
    """
    if study is None:
        raise IeOpsError('Thiếu quan sát bấm giờ.')

    assert_smv_positive(study.calculated_smv, label=f'{study.study_id} CALCULATED_SMV')

    if abs(study.variance_pct or 0) > VARIANCE_LIMIT_PCT:
        require_variance_explanation(
            study.variance_pct,
            variance_explanation or study.variance_explanation,
            label=study.study_id,
        )
        study.variance_explanation = (variance_explanation or study.variance_explanation)[:500]

    study.approval_status = SxTimeStudy.APPROVAL_APPROVED
    if study.operation_id is None:
        study.operation = resolve_operation(study.op_code, study.op_rev)
    study.save(update_fields=['approval_status', 'variance_explanation', 'operation'])

    result = ApproveTimeStudyResult(study_id=study.study_id)
    op_code = (study.op_code or '').strip()
    style_code = (study.style_code or '').strip()
    if not op_code:
        result.warnings.append('Thiếu mã công đoạn — chỉ đánh dấu duyệt, không cập nhật SMV.')
        return result

    qs = SxTimeStudy.objects.filter(
        approval_status=SxTimeStudy.APPROVAL_APPROVED,
        op_code=op_code,
        calculated_smv__gt=0,
    )
    if style_code:
        qs = qs.filter(style_code=style_code)

    sample_count = qs.count()
    avg_smv = qs.aggregate(avg_smv=Avg('calculated_smv'))['avg_smv']
    if not avg_smv or sample_count == 0:
        result.warnings.append('Chưa có SMV tính toán hợp lệ để cập nhật.')
        return result

    new_smv = assert_smv_positive(avg_smv, label='SMV trung bình duyệt')
    result.new_smv = new_smv
    result.sample_count = sample_count

    for row in qs:
        row.current_routing_smv = new_smv
        row.recompute()
        row.save(update_fields=[
            'current_routing_smv',
            'variance_pct',
            'net_observed_sec',
            'normal_time_sec',
            'standard_time_sec',
            'calculated_smv',
        ])

    if update_routing and style_code:
        lines = list(
            SxRoutingLine.objects.filter(
                routing__style_code=style_code,
                routing__is_active=True,
            ).filter(_match_op_codes(op_code)).select_related('routing')
        )
        skipped_locked = 0
        for line in lines:
            if is_routing_locked(line.routing):
                skipped_locked += 1
                continue
            old_lib = line.library_unit_smv or Decimal('0')
            line.applied_unit_smv = new_smv
            line.recompute()
            if abs(line.smv_variance_pct or 0) > VARIANCE_LIMIT_PCT:
                expl = (variance_explanation or study.variance_explanation or '').strip()
                require_variance_explanation(line.smv_variance_pct, expl, label=line.op_code)
                line.variance_explanation = expl[:500]
            line.save()
            if line.routing.approval_status == SxRouting.APPROVAL_APPROVED:
                line.routing.approval_status = SxRouting.APPROVAL_PENDING
                line.routing.save(update_fields=['approval_status', 'updated_at'])
            result.routing_lines_updated += 1
        if skipped_locked:
            result.warnings.append(
                f'{skipped_locked} dòng routing đã khóa (gắn lệnh SX) — bỏ qua, hãy tạo REV mới.'
            )
        if result.routing_lines_updated == 0 and not skipped_locked:
            result.warnings.append(
                f'Không tìm thấy dòng routing active cho {style_code} / {op_code}.'
            )

    if update_library:
        op = study.operation
        if op is None:
            op = SxOperation.objects.filter(_match_op_codes(op_code), op_rev=study.op_rev or 'R01').first()
        if op is None:
            op = SxOperation.objects.filter(_match_op_codes(op_code)).order_by('-op_rev').first()
        if op is None:
            result.warnings.append(f'Không tìm thấy công đoạn thư viện {op_code}.')
        else:
            if op.status == SxOperation.STATUS_APPROVED:
                result.warnings.append(
                    f'{op.op_code}/{op.op_rev} đã duyệt — không sửa đè SMV thư viện; tạo OP_REV mới nếu cần.'
                )
            else:
                op.base_smv_min = new_smv
                op.save(update_fields=['base_smv_min', 'updated_at'])
                result.library_updated = True

    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event

    log_ie_event(
        action=SxIeAuditLog.ACTION_APPROVE if result.routing_lines_updated == 0 and not result.library_updated
        else SxIeAuditLog.ACTION_SMV_CHANGE,
        summary=(
            f'Duyệt time study {study.study_id} → SMV {new_smv} '
            f'(routing {result.routing_lines_updated} dòng'
            f'{", thư viện" if result.library_updated else ""})'
        ),
        object_type='SxTimeStudy',
        object_id=study.pk,
        object_repr=study.study_id,
        changes={
            'new_smv': str(new_smv),
            'sample_count': sample_count,
            'routing_lines_updated': result.routing_lines_updated,
            'library_updated': result.library_updated,
        },
        user=user,
    )
    return result


@transaction.atomic
def reject_time_study(*, study: SxTimeStudy, status: str = SxTimeStudy.APPROVAL_REJECTED) -> SxTimeStudy:
    if status not in {
        SxTimeStudy.APPROVAL_REJECTED,
        SxTimeStudy.APPROVAL_REMEASURE,
        SxTimeStudy.APPROVAL_PENDING,
    }:
        raise IeOpsError('Trạng thái duyệt không hợp lệ.')
    study.approval_status = status
    study.save(update_fields=['approval_status'])
    return study
