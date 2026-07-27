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

    op = SxOperation.objects.filter(op_code=op_code).order_by('-op_rev').first()
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

    return SxTimeStudy.objects.create(
        study_id=sid,
        study_date=date.today(),
        style_code=(style_code or '')[:60],
        operation=op,
        op_code=op_code[:30],
        op_rev=(op_rev or 'R01')[:10],
        op_name_vi=(op_name_vi or '')[:200],
        observed_cycle_sec=observed_cycle_sec,
        abnormal_sec=abnormal_sec if abnormal_sec is not None else Decimal('0'),
        performance_rating=performance_rating if performance_rating is not None else Decimal('1'),
        allowance_pct=allowance_pct if allowance_pct is not None else Decimal('0'),
        current_routing_smv=current_routing_smv if current_routing_smv is not None else Decimal('0'),
        notes='Tạo tay (không import Excel)',
    )


@transaction.atomic
def apply_routing_to_bom(*, bom: BomVersion, routing: SxRouting, replace: bool = True) -> ApplyRoutingResult:
    """Gắn routing vào BOM và đồng bộ ProcessStep từ dòng routing.

    - std_time_minutes = tổng SMV công đoạn (qty × SMV áp dụng)
    - norm_per_hour = 60 / SMV áp dụng (cái/giờ trên 1 đơn vị cơ sở)
    - Routing trống: chỉ gắn BOM, giữ nguyên công đoạn hiện có (nhập tay).
    - Phát hành: SMV áp dụng phải > 0 trên mọi dòng có công đoạn.
    """
    if bom is None:
        raise IeOpsError('Thiếu BOM.')
    if routing is None:
        raise IeOpsError('Thiếu routing.')

    lines = list(routing.lines.select_related('operation', 'work_center').order_by('seq_no'))
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
            work_center=line.work_center,
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
    op = SxOperation.objects.filter(op_code=op_code, op_rev=op_rev).first()
    if op is None:
        op = SxOperation.objects.filter(op_code=op_code).order_by('-op_rev').first()
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
    from san_xuat.hub_models import SxWorkCenter
    wc = SxWorkCenter.objects.filter(code=(work_center_code or '').strip()).first() if work_center_code else None

    line = None
    if line_pk:
        line = routing.lines.filter(pk=line_pk).first()
        if line is None:
            raise IeOpsError('Không tìm thấy dòng routing.')
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
    line.work_center_code = (work_center_code or (wc.code if wc else ''))[:40]
    line.notes = (notes or '')[:255]
    line.recompute()
    if abs(line.smv_variance_pct or 0) > VARIANCE_LIMIT_PCT:
        require_variance_explanation(line.smv_variance_pct, variance_explanation, label=op_code)
        line.variance_explanation = (variance_explanation or '')[:500]
    elif variance_explanation:
        line.variance_explanation = variance_explanation[:500]
    line.save()
    _mark_routing_pending(routing)
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
    """Số liệu dashboard kiểu sheet 07_DASHBOARD."""
    from django.db.models import Count, Sum, Q as DQ

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
        )
        .order_by('style_code', 'routing_rev')
    ):
        style_rows.append({
            'style_code': r.style_code,
            'product_family': r.product_family or r.style_name,
            'routing_id': r.routing_id,
            'routing_rev': r.routing_rev,
            'pk': r.pk,
            'approval_status': r.approval_status,
            'operation_count': r.n_lines or 0,
            'total_smv': r.sum_smv or Decimal('0'),
            'sewing_smv': r.sew_smv or Decimal('0'),
        })

    high_var = list(
        SxRoutingLine.objects.filter(
            DQ(smv_variance_pct__gt=VARIANCE_LIMIT_PCT) | DQ(smv_variance_pct__lt=-VARIANCE_LIMIT_PCT)
        )
        .select_related('routing')
        .order_by('-smv_variance_pct')[:40]
    )
    pending_ops = SxOperation.objects.exclude(status=SxOperation.STATUS_APPROVED).count()
    pending_routings = SxRouting.objects.exclude(approval_status=SxRouting.APPROVAL_APPROVED).count()
    zero_smv_lines = SxRoutingLine.objects.filter(applied_unit_smv__lte=0).count()

    return {
        'style_rows': style_rows,
        'high_var_lines': high_var,
        'pending_ops': pending_ops,
        'pending_routings': pending_routings,
        'zero_smv_lines': zero_smv_lines,
        'high_var_count': SxRoutingLine.objects.filter(
            DQ(smv_variance_pct__gt=VARIANCE_LIMIT_PCT) | DQ(smv_variance_pct__lt=-VARIANCE_LIMIT_PCT)
        ).count(),
        'groups': SxOperationGroup.objects.count(),
        'operations': SxOperation.objects.count(),
        'routings': SxRouting.objects.count(),
        'routing_lines': SxRoutingLine.objects.count(),
        'time_studies': SxTimeStudy.objects.count(),
        'variance_limit': VARIANCE_LIMIT_PCT,
    }


@transaction.atomic
def approve_time_study(
    *,
    study: SxTimeStudy,
    update_library: bool = False,
    update_routing: bool = True,
    variance_explanation: str = '',
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
    study.save(update_fields=['approval_status', 'variance_explanation'])

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
