"""Nghiệp vụ IE: áp routing vào BOM, duyệt bấm giờ cập nhật SMV routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Avg, Q

from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine, SxTimeStudy
from san_xuat.models import BomVersion, ProcessStep
from san_xuat.services.process_catalog import ensure_process_name


class IeOpsError(Exception):
    pass


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
def approve_time_study(
    *,
    study: SxTimeStudy,
    update_library: bool = False,
    update_routing: bool = True,
) -> ApproveTimeStudyResult:
    """Duyệt một quan sát bấm giờ và (tuỳ chọn) cập nhật SMV routing / thư viện.

    SMV mới = trung bình các quan sát ĐÃ DUYỆT cùng (style_code, op_code) có SMV > 0.
    """
    if study is None:
        raise IeOpsError('Thiếu quan sát bấm giờ.')

    study.approval_status = SxTimeStudy.APPROVAL_APPROVED
    study.save(update_fields=['approval_status'])

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

    new_smv = _q(Decimal(str(avg_smv)), '0.0001')
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
        lines = SxRoutingLine.objects.filter(
            routing__style_code=style_code,
            routing__is_active=True,
        ).filter(_match_op_codes(op_code))
        for line in lines:
            line.applied_unit_smv = new_smv
            line.save()
            result.routing_lines_updated += 1
        if result.routing_lines_updated == 0:
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
