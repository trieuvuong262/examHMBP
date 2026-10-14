"""Ba luồng QC xưởng: inline (đang may), endline (cuối chuyền), preaudit (trước audit khách)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxQcFlowCheck, SxQcFlowDefectLine
from san_xuat.services.progress_template import (
    TEAM_SLUGS,
    steps_for_group,
    team_by_slug,
    team_slug_for_process_label,
)
from san_xuat.services.qc import QcError, _next_code

FLOW_META = {
    SxQcFlowCheck.FLOW_INLINE: {
        'label': 'QC inline',
        'headline': 'Kiểm 100% trên chuyền',
        'blurb': 'Theo công đoạn và theo size. Ghi lỗi để sửa tại chỗ, không chốt lô.',
        'prefix': 'QCI',
    },
    SxQcFlowCheck.FLOW_ENDLINE: {
        'label': 'QC endline',
        'headline': 'Kiểm 100% hàng ra chuyền',
        'blurb': 'Theo size, chốt Đạt hoặc Không đạt. Một phiếu Đạt là đủ để nhập thành phẩm.',
        'prefix': 'QCE',
    },
    SxQcFlowCheck.FLOW_PREAUDIT: {
        'label': 'QC preaudit',
        'headline': 'Lấy mẫu ngẫu nhiên',
        'blurb': 'AQL 2.5, mức II. Số mẫu do hệ thống tính, không sửa tay.',
        'prefix': 'QCP',
    },
}

FLOWS = (
    SxQcFlowCheck.FLOW_INLINE,
    SxQcFlowCheck.FLOW_ENDLINE,
    SxQcFlowCheck.FLOW_PREAUDIT,
)


def inline_stages_for_team(team_slug: str) -> list[str]:
    """Công đoạn chuẩn của một tổ. Cùng tên trong tổ chỉ hiện một lần."""
    meta = team_by_slug(team_slug)
    group_key = (meta or {}).get('group_key') or ''
    if not group_key:
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for step in steps_for_group(group_key):
        key = step.label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(step.label)
    return labels


def inline_stages_by_team() -> dict[str, list[str]]:
    return {slug: inline_stages_for_team(slug) for slug, *_rest in TEAM_SLUGS}


def stage_belongs_to_team(stage_name: str, team_slug: str) -> bool:
    owner = team_slug_for_process_label(stage_name)
    return bool(owner) and owner == (team_slug or '').strip().lower()


def flow_meta(flow: str) -> dict:
    try:
        return FLOW_META[flow]
    except KeyError as exc:
        raise QcError('Luồng QC không hợp lệ.') from exc


def _q(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else '0')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
    except Exception:
        return Decimal('0.00')


def _code_for(flow: str) -> str:
    return _next_code(flow_meta(flow)['prefix'], SxQcFlowCheck)


@dataclass
class FlowBoardRow:
    mo: SxProductionOrder
    inline_count: int
    endline: SxQcFlowCheck | None
    preaudit: SxQcFlowCheck | None
    product_image_url: str = ''
    product_image_urls_json: str = '[]'


def aql_fixed_bands() -> list[dict]:
    """Các khoảng cỡ lô của AQL 2.5 mức II, để màn preaudit cập nhật số mẫu khi gõ."""
    from san_xuat.services.aql import _CODE_TABLE, aql_sample_plan

    bands = []
    start = 1
    uppers = [row[0] for row in _CODE_TABLE]
    for upper in uppers:
        plan = aql_sample_plan(lot_size=upper, aql=Decimal('2.5'), inspection_level='II')
        bands.append({
            'from': start,
            'to': upper,
            'sample': 10 ** 9 if plan.full_inspection else plan.sample_size,
            'accept': plan.accept,
            'reject': plan.reject,
            'letter': plan.code_letter,
        })
        start = upper + 1
    plan = aql_sample_plan(lot_size=uppers[-1] + 1, aql=Decimal('2.5'), inspection_level='II')
    bands.append({
        'from': start,
        'to': None,
        'sample': plan.sample_size,
        'accept': plan.accept,
        'reject': plan.reject,
        'letter': plan.code_letter,
    })
    return bands


def _is_pass(item: SxQcFlowCheck) -> bool:
    return item.status == SxQcFlowCheck.STATUS_DONE and item.result == SxQcFlowCheck.RESULT_PASS


def _prefer_pass(current: SxQcFlowCheck | None, candidate: SxQcFlowCheck) -> SxQcFlowCheck:
    """Phiếu Đạt được ưu tiên — một phiếu Đạt là đủ, phiếu Không đạt sau đó không khóa lại."""
    if _is_pass(candidate) and (current is None or not _is_pass(current)):
        return candidate
    if current is not None and _is_pass(current) and not _is_pass(candidate):
        return current
    return _prefer(current, candidate)


def _prefer(current: SxQcFlowCheck | None, candidate: SxQcFlowCheck) -> SxQcFlowCheck:
    if current is None:
        return candidate
    current_done = current.status == SxQcFlowCheck.STATUS_DONE
    candidate_done = candidate.status == SxQcFlowCheck.STATUS_DONE
    if candidate_done and not current_done:
        return candidate
    if current_done and not candidate_done:
        return current
    if (candidate.checked_on, candidate.pk) >= (current.checked_on, current.pk):
        return candidate
    return current


def flow_board(mos: list[SxProductionOrder]) -> list[FlowBoardRow]:
    if not mos:
        return []
    checks = (
        SxQcFlowCheck.objects.filter(is_demo=False, production_order_id__in=[m.pk for m in mos])
        .order_by('production_order_id', '-checked_on', '-pk')
    )
    inline_count: dict[int, int] = {}
    endline: dict[int, SxQcFlowCheck] = {}
    preaudit: dict[int, SxQcFlowCheck] = {}
    for item in checks:
        mo_id = item.production_order_id
        if item.flow == SxQcFlowCheck.FLOW_INLINE:
            inline_count[mo_id] = inline_count.get(mo_id, 0) + 1
        elif item.flow == SxQcFlowCheck.FLOW_ENDLINE:
            endline[mo_id] = _prefer_pass(endline.get(mo_id), item)
        elif item.flow == SxQcFlowCheck.FLOW_PREAUDIT:
            preaudit[mo_id] = _prefer(preaudit.get(mo_id), item)
    rows = [
        FlowBoardRow(
            mo=mo,
            inline_count=inline_count.get(mo.pk, 0),
            endline=endline.get(mo.pk),
            preaudit=preaudit.get(mo.pk),
        )
        for mo in mos
    ]
    _attach_board_images(rows)
    return rows


def _attach_board_images(rows: list[FlowBoardRow]) -> None:
    import json

    from san_xuat.services.products import product_gallery_map

    gallery = product_gallery_map(row.mo.product_code for row in rows)
    for row in rows:
        urls = gallery.get((row.mo.product_code or '').casefold(), [])
        row.product_image_url = urls[0] if urls else ''
        row.product_image_urls_json = json.dumps(urls, ensure_ascii=False)


def latest_done_endline(*, mo: SxProductionOrder) -> SxQcFlowCheck | None:
    return (
        SxQcFlowCheck.objects.filter(
            is_demo=False,
            production_order=mo,
            flow=SxQcFlowCheck.FLOW_ENDLINE,
            status=SxQcFlowCheck.STATUS_DONE,
        )
        .order_by('-checked_on', '-pk')
        .first()
    )


def passed_endline(*, mo: SxProductionOrder) -> SxQcFlowCheck | None:
    """Một phiếu endline đã chốt Đạt — đủ để nhập thành phẩm, không cần đủ SL lệnh."""
    return (
        SxQcFlowCheck.objects.filter(
            is_demo=False,
            production_order=mo,
            flow=SxQcFlowCheck.FLOW_ENDLINE,
            status=SxQcFlowCheck.STATUS_DONE,
            result=SxQcFlowCheck.RESULT_PASS,
        )
        .order_by('-checked_on', '-pk')
        .first()
    )


def apply_preaudit_plan(check: SxQcFlowCheck) -> None:
    from san_xuat.services.aql import AqlError, aql_sample_plan

    lot = check.qty_lot or Decimal('0')
    if lot <= 0:
        check.sample_size = 0
        check.accept_qty = 0
        return
    try:
        plan = aql_sample_plan(
            lot_size=lot,
            aql=check.aql_level or Decimal('2.5'),
            inspection_level=(check.inspection_level or 'II').strip() or 'II',
        )
    except AqlError:
        check.sample_size = 0
        check.accept_qty = 0
        return
    check.sample_size = plan.sample_size
    check.accept_qty = plan.accept
    if (check.qty_checked or Decimal('0')) <= 0:
        check.qty_checked = Decimal(plan.sample_size)


def order_size_plan(mo: SxProductionOrder | None) -> list[dict]:
    """Size trên lệnh, gộp SL nếu nhiều màu cùng size."""
    if mo is None:
        return [{'size_label': '—', 'qty_order': Decimal('0')}]
    totals: dict[str, Decimal] = {}
    order: list[str] = []
    for line in mo.lines.all():
        label = (line.size_label or '').strip() or '—'
        if label not in totals:
            order.append(label)
            totals[label] = Decimal('0')
        totals[label] += line.qty or Decimal('0')
    if not order:
        return [{'size_label': '—', 'qty_order': mo.qty or Decimal('0')}]
    return [{'size_label': label, 'qty_order': totals[label]} for label in order]


def size_form_rows(mo: SxProductionOrder | None, check: SxQcFlowCheck | None, post=None) -> list[dict]:
    plan = {row['size_label']: row['qty_order'] for row in order_size_plan(mo)}
    saved = {}
    if check is not None:
        for line in check.size_lines.all():
            saved[line.size_label] = line
    if post is not None:
        parsed = {row['size_label']: row for row in parse_size_rows(post)}
    else:
        parsed = {}
    labels = list(dict.fromkeys([*plan.keys(), *saved.keys(), *parsed.keys()]))
    rows = []
    for label in labels:
        src = parsed.get(label) or saved.get(label)
        rows.append({
            'size_label': label,
            'qty_order': plan.get(label, getattr(src, 'qty_order', None) or Decimal('0')),
            'qty_checked': '' if src is None else src['qty_checked'] if isinstance(src, dict) else src.qty_checked,
            'qty_pass': '' if src is None else src['qty_pass'] if isinstance(src, dict) else src.qty_pass,
            'qty_repair': '' if src is None else src['qty_repair'] if isinstance(src, dict) else src.qty_repair,
            'qty_fail': '' if src is None else src['qty_fail'] if isinstance(src, dict) else src.qty_fail,
        })
    return rows


def parse_size_rows(post) -> list[dict]:
    labels = post.getlist('size_label')
    orders = post.getlist('size_order')
    checked = post.getlist('size_checked')
    passed = post.getlist('size_pass')
    repair = post.getlist('size_repair')
    fail = post.getlist('size_fail')
    rows = []
    seen = set()
    for idx, raw_label in enumerate(labels):
        label = (raw_label or '').strip() or '—'
        if label in seen:
            continue
        seen.add(label)
        rows.append({
            'size_label': label,
            'qty_order': _q(orders[idx] if idx < len(orders) else 0),
            'qty_checked': _q(checked[idx] if idx < len(checked) else 0),
            'qty_pass': _q(passed[idx] if idx < len(passed) else 0),
            'qty_repair': _q(repair[idx] if idx < len(repair) else 0),
            'qty_fail': _q(fail[idx] if idx < len(fail) else 0),
        })
    return rows


def _severity_from_catalog(raw: str) -> str:
    text = (raw or '').strip().lower()
    if text in {'minor', 'nhe', 'nhẹ', 'light'}:
        return SxQcFlowDefectLine.SEVERITY_MINOR
    if text in {'critical', 'nghiem trong', 'nghiêm trọng'}:
        return SxQcFlowDefectLine.SEVERITY_CRITICAL
    return SxQcFlowDefectLine.SEVERITY_MAJOR


def parse_defect_rows(post) -> list[dict]:
    from san_xuat.hub_models import SxQcDefect

    ids = post.getlist('defect_id')
    sizes = post.getlist('defect_size')
    qtys = post.getlist('defect_qty')
    wanted = []
    for raw in ids:
        if str(raw).isdigit():
            wanted.append(int(raw))
    catalog = {
        item.pk: item
        for item in SxQcDefect.objects.filter(pk__in=wanted, is_demo=False, is_active=True)
    }
    rows = []
    for idx, raw_id in enumerate(ids):
        if not str(raw_id).isdigit():
            continue
        defect = catalog.get(int(raw_id))
        if defect is None:
            continue
        qty = _q(qtys[idx] if idx < len(qtys) else '1')
        if qty <= 0:
            qty = Decimal('1.00')
        rows.append({
            'defect': defect,
            'defect_id': defect.pk,
            'defect_name': defect.name,
            'size_label': (sizes[idx] if idx < len(sizes) else '').strip(),
            'qty': qty,
            'severity': _severity_from_catalog(defect.severity),
        })
    return rows


def _replace_defects(check: SxQcFlowCheck, rows: list[dict]) -> None:
    check.defect_lines.all().delete()
    SxQcFlowDefectLine.objects.bulk_create([
        SxQcFlowDefectLine(
            sheet=check,
            defect=row['defect'],
            defect_name=row['defect_name'],
            size_label=row.get('size_label') or '',
            qty=row['qty'],
            severity=row['severity'],
        )
        for row in rows
    ])


def _replace_sizes(check: SxQcFlowCheck, rows: list[dict]) -> None:
    from san_xuat.hub_models import SxQcFlowSizeLine

    check.size_lines.all().delete()
    SxQcFlowSizeLine.objects.bulk_create([
        SxQcFlowSizeLine(sheet=check, **row) for row in rows
    ])


def apply_size_totals(check: SxQcFlowCheck, size_rows: list[dict]) -> list[dict]:
    kept = []
    totals = {
        'qty_checked': Decimal('0'),
        'qty_pass': Decimal('0'),
        'qty_repair': Decimal('0'),
        'qty_fail': Decimal('0'),
    }
    for row in size_rows:
        checked = row['qty_checked']
        passed = row['qty_pass']
        repair = row['qty_repair']
        fail = row['qty_fail']
        if checked == passed == repair == fail == Decimal('0'):
            continue
        if passed + repair + fail != checked:
            raise QcError(
                f"Size {row['size_label']}: SL đạt + SL sửa + SL lỗi phải bằng SL kiểm."
            )
        kept.append(row)
        totals['qty_checked'] += checked
        totals['qty_pass'] += passed
        totals['qty_repair'] += repair
        totals['qty_fail'] += fail
    if not kept:
        raise QcError('Nhập số lượng đã kiểm theo size.')
    for key, value in totals.items():
        setattr(check, key, value)
    return kept


def validate_quantities(check: SxQcFlowCheck) -> None:
    if check.flow == SxQcFlowCheck.FLOW_INLINE:
        if (check.qty_checked or Decimal('0')) <= 0:
            raise QcError('QC inline cần số lượng đã kiểm.')
        if not (check.team_slug or '').strip():
            raise QcError('QC inline cần chọn tổ.')
        if not (check.stage_name or '').strip():
            raise QcError('QC inline cần chọn công đoạn đang kiểm.')
        if not stage_belongs_to_team(check.stage_name, check.team_slug):
            raise QcError('Công đoạn không thuộc tổ đã chọn.')
        return
    if check.flow == SxQcFlowCheck.FLOW_ENDLINE:
        checked = check.qty_checked or Decimal('0')
        if checked <= 0:
            raise QcError('QC endline cần số lượng đã kiểm.')
        parts = (check.qty_pass or Decimal('0')) + (check.qty_repair or Decimal('0')) + (check.qty_fail or Decimal('0'))
        if parts != checked:
            raise QcError('SL đạt + SL sửa + SL lỗi phải bằng SL kiểm.')
        return
    if (check.qty_lot or Decimal('0')) <= 0:
        raise QcError('QC preaudit cần cỡ lô.')
    if (check.qty_checked or Decimal('0')) <= 0:
        raise QcError('QC preaudit cần số lượng mẫu đã kiểm.')


@transaction.atomic
def save_flow_check(
    *,
    flow: str,
    check: SxQcFlowCheck | None,
    cleaned: dict,
    defect_rows: list[dict],
    size_rows: list[dict] | None = None,
    action: str,
    user,
) -> SxQcFlowCheck:
    flow_meta(flow)
    if check is not None and check.flow != flow:
        raise QcError('Phiếu không thuộc luồng này.')
    if check is not None and check.status == SxQcFlowCheck.STATUS_DONE:
        raise QcError('Phiếu đã chốt, không sửa được.')

    mo = cleaned['production_order']
    creating = check is None
    if creating:
        check = SxQcFlowCheck(
            code=_code_for(flow),
            flow=flow,
            is_demo=False,
            created_by=user if getattr(user, 'is_authenticated', False) else None,
        )
    check.production_order = mo
    check.product_code = mo.product_code or ''
    check.product_name = mo.product_name or ''
    check.team_slug = (cleaned.get('team_slug') or '').strip().lower()
    check.stage_name = (cleaned.get('stage_name') or '').strip()
    check.checked_on = cleaned.get('checked_on') or timezone.localdate()
    check.notes = (cleaned.get('notes') or '').strip()
    kept_sizes: list[dict] = []

    if flow == SxQcFlowCheck.FLOW_PREAUDIT:
        check.qty_lot = _q(cleaned.get('qty_lot'))
        check.aql_level = Decimal('2.5')
        check.inspection_level = 'II'
        check.team_slug = ''
        check.stage_name = ''
        apply_preaudit_plan(check)
        check.qty_checked = Decimal(check.sample_size or 0)
        check.qty_fail = sum((row['qty'] for row in defect_rows), Decimal('0'))
        check.qty_pass = Decimal('0')
        check.qty_repair = Decimal('0')
    else:
        check.qty_lot = Decimal('0')
        check.sample_size = 0
        check.accept_qty = 0
        check.aql_level = Decimal('2.5')
        check.inspection_level = ''
        kept_sizes = apply_size_totals(check, size_rows or [])

    validate_quantities(check)

    if action == 'pass':
        if flow == SxQcFlowCheck.FLOW_INLINE:
            raise QcError('QC inline chỉ ghi nhận, không chốt Đạt/Không đạt.')
        if flow == SxQcFlowCheck.FLOW_ENDLINE and (check.qty_fail or Decimal('0')) > 0:
            raise QcError('Còn hàng lỗi — sửa hết hoặc chốt Không đạt.')
        if flow == SxQcFlowCheck.FLOW_PREAUDIT and (check.qty_fail or Decimal('0')) > Decimal(check.accept_qty or 0):
            raise QcError(
                f'Số lỗi {int(check.qty_fail)} vượt mức chấp nhận {check.accept_qty} '
                f'(mẫu {check.sample_size}, AQL 2.5, mức II).'
            )
        check.result = SxQcFlowCheck.RESULT_PASS
        check.status = SxQcFlowCheck.STATUS_DONE
    elif action == 'fail':
        if flow == SxQcFlowCheck.FLOW_INLINE:
            raise QcError('QC inline chỉ ghi nhận, không chốt Đạt/Không đạt.')
        check.result = SxQcFlowCheck.RESULT_FAIL
        check.status = SxQcFlowCheck.STATUS_DONE
    elif action == 'save' and flow == SxQcFlowCheck.FLOW_INLINE:
        check.result = SxQcFlowCheck.RESULT_NOTED
        check.status = SxQcFlowCheck.STATUS_DONE
    else:
        check.result = SxQcFlowCheck.RESULT_OPEN
        check.status = SxQcFlowCheck.STATUS_DRAFT

    check.save()
    _replace_defects(check, defect_rows)
    if flow != SxQcFlowCheck.FLOW_PREAUDIT:
        _replace_sizes(check, kept_sizes)
    return check


def blank_defect_slots(check: SxQcFlowCheck | None, *, slots: int = 4) -> list[dict]:
    rows = []
    if check is not None:
        for line in check.defect_lines.all():
            rows.append({
                'defect_id': line.defect_id or '',
                'defect_name': line.defect_name,
                'size_label': line.size_label,
                'qty': line.qty,
                'severity': line.severity,
            })
    while len(rows) < slots:
        rows.append({
            'defect_id': '',
            'defect_name': '',
            'size_label': '',
            'qty': '',
            'severity': SxQcFlowDefectLine.SEVERITY_MAJOR,
        })
    return rows
