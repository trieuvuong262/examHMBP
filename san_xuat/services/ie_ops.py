"""Nghiệp vụ IE: áp routing vào BOM, duyệt bấm giờ cập nhật SMV routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Avg, Q

from san_xuat.ie_models import SxOperation, SxRouting, SxRoutingLine, SxTimeStudy
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
    warnings: list[str] = field(default_factory=list)


@dataclass
class ApproveTimeStudyResult:
    study_id: str = ''
    new_smv: Decimal = Decimal('0')
    sample_count: int = 0
    routing_lines_updated: int = 0
    library_updated: bool = False
    warnings: list[str] = field(default_factory=list)


@transaction.atomic
def apply_routing_to_bom(*, bom: BomVersion, routing: SxRouting, replace: bool = True) -> ApplyRoutingResult:
    """Gắn routing vào BOM và đồng bộ ProcessStep từ dòng routing.

    - std_time_minutes = tổng SMV công đoạn (qty × SMV áp dụng)
    - norm_per_hour = 60 / SMV áp dụng (cái/giờ trên 1 đơn vị cơ sở)
    """
    if bom is None:
        raise IeOpsError('Thiếu BOM.')
    if routing is None:
        raise IeOpsError('Thiếu routing.')

    lines = list(routing.lines.select_related('operation', 'work_center').order_by('seq_no'))
    if not lines:
        raise IeOpsError(f'Routing {routing.routing_id} chưa có công đoạn.')

    result = ApplyRoutingResult(routing_id=routing.routing_id)
    bom.routing = routing
    bom.save(update_fields=['routing', 'updated_at'])

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
