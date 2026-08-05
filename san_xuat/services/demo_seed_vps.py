"""Seed dữ liệu demo Sản xuất trên VPS — hiển thị trên UI, không đụng kho NPL / KiotViet."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxCostType,
    SxDetailPlan,
    SxDetailPlanLine,
    SxDisassemblyOrder,
    SxDowntimeEvent,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxMaterialIssueRequestLine,
    SxMaterialPlan,
    SxMaterialPlanLine,
    SxNcrCase,
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxNplSurplus,
    SxOrderPlanCost,
    SxOrderPlanCostLine,
    SxOverallPlan,
    SxOverallPlanLine,
    SxPackingRecord,
    SxProductGroup,
    SxProductionOrder,
    SxProductionStat,
    SxPurchaseOrder,
    SxPurchaseOrderLine,
    SxQcAlert,
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcInspection,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardSet,
    SxStandardCostLine,
    SxStandardCostSheet,
    SxSubcontractOrder,
    SxTeamHrMap,
    SxWipHandover,
    SxWipReturn,
    SxWorkAssignment,
    SxWorkCenter,
)
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.costing import compute_costing
from san_xuat.services.demo_seed import (
    DEMO_NOTE_PREFIX,
    discover_kv_product_codes,
    resolve_existing_material,
    seed_demo_tech_doc,
)
from san_xuat.services.demo_seed_hub import HUB_DEMO_MODELS_DELETE_ORDER, clear_demo_hub

VPS_DEMO_NOTE = '[VPS-DEMO SX]'
VPS_DEMO_NOTE_KHSX = '[VPS-DEMO KHSX]'
VPS_DEMO_NOTE_PREFIXES = (VPS_DEMO_NOTE, VPS_DEMO_NOTE_KHSX)

VPS_DELETE_ORDER = (
    SxNcrCase,
    SxQcAlert,
    SxDowntimeEvent,
    SxWorkAssignment,
    SxPackingRecord,
    SxSubcontractOrder,
    SxTeamHrMap,
    SxWorkCenter,
    SxProductGroup,
    SxCostType,
    *HUB_DEMO_MODELS_DELETE_ORDER,
)


def _demo_flag(visible: bool) -> bool:
    return not visible


def _notes(visible: bool, extra: str = '') -> str:
    base = VPS_DEMO_NOTE if visible else DEMO_NOTE_PREFIX
    return f'{base} {extra}'.strip() if extra else base


@transaction.atomic
def clear_vps_demo(*, include_legacy_demo: bool = True) -> dict[str, int]:
    """Xóa dữ liệu seed VPS / KHSX demo (notes / mã *-VPS-* / *-KHSX-DEMO*).

    Không đụng phiếu kho NPL (`kho_npl`) hay chứng từ KiotViet.
    """
    counts: dict[str, int] = {}
    code_q = (
        models.Q(code__icontains='-VPS-')
        | models.Q(code__icontains='VPS-2026')
        | models.Q(code__icontains='KHSX-DEMO')
    )
    notes_q = models.Q()
    for prefix in VPS_DEMO_NOTE_PREFIXES:
        notes_q |= models.Q(notes__startswith=prefix)

    for model in VPS_DELETE_ORDER:
        q = code_q if hasattr(model, 'code') else models.Q(pk__in=[])
        if hasattr(model, 'notes'):
            q = q | notes_q
        deleted, _ = model.objects.filter(q).delete()
        if deleted:
            counts[model.__name__] = deleted
    # Không xóa ProductTechDoc theo notes VPS — tránh mất hồ sơ SP thật đã gắn nhãn seed.
    if include_legacy_demo:
        legacy = clear_demo_hub()
        counts['legacy_hub'] = legacy
        legacy_docs, _ = ProductTechDoc.objects.filter(notes__startswith=DEMO_NOTE_PREFIX).delete()
        if legacy_docs:
            counts['legacy_tech_docs'] = legacy_docs
    return counts


def _product_name(code: str) -> str:
    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    return doc.product_name if doc else code


def _active_bom(code: str) -> BomVersion | None:
    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    if not doc:
        return None
    return doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE).first()


@transaction.atomic
def seed_vps_hub(*, product_codes: list[str], user=None, visible: bool = True) -> dict:
    """Tạo chuỗi dữ liệu SX phong phú — hiển thị trên UI khi visible=True."""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=20)
    demo = _demo_flag(visible)
    note = _notes(visible)
    stats: dict[str, int] = {}

    primary = product_codes[0] if product_codes else 'SP008073'
    secondary = product_codes[1] if len(product_codes) > 1 else primary
    tertiary = product_codes[2] if len(product_codes) > 2 else secondary

    # --- Năng lực / map HR: theo bộ phận thật phòng SẢN XUẤT ---
    from san_xuat.services.capacity_from_hrm import sync_capacity_from_hrm

    sync_stats = sync_capacity_from_hrm(reset_capacity=True, deactivate_legacy=True)
    stats['work_centers'] = sync_stats.created + sync_stats.updated
    stats['team_hr_maps'] = sync_stats.hr_maps

    def _wc(*name_parts: str) -> SxWorkCenter | None:
        qs = SxWorkCenter.objects.filter(is_active=True, is_demo=False)
        for part in name_parts:
            hit = qs.filter(name__icontains=part).order_by('code').first()
            if hit:
                return hit
        return None

    # Tổ theo khối xưởng 7–8–9 (+ hoàn thiện)
    wc_cut = _wc('CẮT', 'TRẢI')
    wc_print = _wc('IN ÉP', 'IN ', 'ÉP')
    wc_may1 = _wc('MAY')
    wc_may2 = (
        SxWorkCenter.objects.filter(is_active=True, is_demo=False, name__icontains='MAY')
        .exclude(pk=getattr(wc_may1, 'pk', None))
        .order_by('code')
        .first()
    )
    wc_iron = _wc('ỦI')
    wc_dg = _wc('GẤP', 'ĐG')
    if not wc_may1:
        raise RuntimeError(
            'Chưa có tổ/chuyền HR (HRD-*). Chạy: python manage.py sync_capacity_from_hrm'
        )
    if not wc_may2:
        wc_may2 = wc_may1
    if not wc_cut:
        wc_cut = wc_may1
    if not wc_print:
        wc_print = wc_may1
    if not wc_iron:
        wc_iron = wc_dg or wc_may1
    if not wc_dg:
        wc_dg = wc_may1

    def _team(wc: SxWorkCenter | None, fallback: str = '') -> str:
        if not wc:
            return fallback
        return (wc.team_label or wc.name or fallback).strip()

    for code, name in [('NHOM-POLO', 'Polo / T-shirt'), ('NHOM-SHORT', 'Quần short')]:
        SxProductGroup.objects.update_or_create(
            code=code,
            defaults={'is_demo': demo, 'name': name, 'is_active': True, 'notes': note},
        )
    stats['product_groups'] = 2

    for code, name, sort in [
        ('CP-VAN-CHUYEN', 'Vận chuyển nội bộ', 10),
        ('CP-BAO-BI', 'Bao bì / tem nhãn', 20),
    ]:
        SxCostType.objects.update_or_create(
            code=code,
            defaults={'is_demo': demo, 'name': name, 'sort_order': sort, 'is_active': True, 'notes': note},
        )
    stats['cost_types'] = 2

    # --- Kế hoạch ---
    overall, _ = SxOverallPlan.objects.update_or_create(
        code='KHTT-2026-Q3-VPS',
        defaults={
            'is_demo': demo,
            'name': 'Kế hoạch SX Q3/2026',
            'date_from': week_start,
            'date_to': week_end,
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': note,
        },
    )
    SxOverallPlanLine.objects.filter(plan=overall).delete()
    for idx, code in enumerate(product_codes[:6]):
        SxOverallPlanLine.objects.create(
            plan=overall,
            product_code=code,
            product_name=_product_name(code),
            qty_required=Decimal('600') + idx * 50,
            qty_planned=Decimal('480') + idx * 40,
            capacity_per_day=Decimal('90'),
        )
    stats['overall_plans'] = 1

    detail, _ = SxDetailPlan.objects.update_or_create(
        code='KHCT-2026-W01-VPS',
        defaults={
            'is_demo': demo,
            'name': 'KH chi tiết tuần 1',
            'overall_plan': overall,
            'date_from': week_start,
            'date_to': week_start + timedelta(days=6),
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': note,
        },
    )
    SxDetailPlanLine.objects.filter(plan=detail).delete()
    # 10 dòng KHCT — trải đều Cắt / In–ép / May / Ủi / Gấp
    wc_cycle = [wc for wc in (wc_cut, wc_print, wc_may1, wc_may2, wc_iron, wc_dg) if wc]
    for day in range(10):
        code = product_codes[day % len(product_codes)]
        wc = wc_cycle[day % len(wc_cycle)]
        team = _team(wc)
        SxDetailPlanLine.objects.create(
            plan=detail,
            plan_date=week_start + timedelta(days=day % 7),
            product_code=code,
            product_name=_product_name(code),
            qty=Decimal('60') + day * 8,
            team_label=team,
            work_center=wc,
        )
    stats['detail_plans'] = 1

    mat_plan, _ = SxMaterialPlan.objects.update_or_create(
        code='KHNVL-2026-Q3-VPS',
        defaults={
            'is_demo': demo,
            'name': 'Nhu cầu NPL theo KHTT',
            'overall_plan': overall,
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': note,
        },
    )
    SxMaterialPlanLine.objects.filter(plan=mat_plan).delete()
    for material_code in ('JP-VAI-COT180-WHT', 'JP-CHI-PES40-WHT', 'JP-TEM-SIZE-JP'):
        material = resolve_existing_material(material_code)
        SxMaterialPlanLine.objects.create(
            plan=mat_plan,
            material_code=material.code if material else material_code,
            material_name=material.name if material else material_code,
            qty_required=Decimal('520'),
            qty_on_hand=Decimal('180'),
            qty_shortfall=Decimal('340'),
        )
    stats['material_plans'] = 1

    pr, _ = SxNplPurchaseRequest.objects.update_or_create(
        code='YCM-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'material_plan': mat_plan,
            'due_date': week_start + timedelta(days=5),
            'status': 'approved',
            'notes': note,
        },
    )
    SxNplPurchaseRequestLine.objects.filter(request=pr).delete()
    SxNplPurchaseRequestLine.objects.create(
        request=pr,
        material_code='JP-VAI-COT180-WHT',
        material_name='Vải cotton trắng',
        qty=Decimal('340'),
    )
    stats['npl_prs'] = 1

    po, _ = SxPurchaseOrder.objects.update_or_create(
        code='DMH-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'supplier_name': 'Công ty TNHH Vải Đồng Nai',
            'purchase_request': pr,
            'status': 'confirmed',
            'notes': note,
        },
    )
    SxPurchaseOrderLine.objects.filter(order=po).delete()
    SxPurchaseOrderLine.objects.create(
        order=po,
        material_code='JP-VAI-COT180-WHT',
        material_name='Vải cotton trắng',
        qty_ordered=Decimal('340'),
        qty_received=Decimal('0'),
    )
    stats['purchase_orders'] = 1

    # --- 10 lệnh SX (khối 7 Cắt → 8 In/thêu/ép → 9 May → hoàn thiện) ---
    team_cut = _team(wc_cut)
    team_print = _team(wc_print)
    team_a = _team(wc_may1)
    team_b = _team(wc_may2, team_a)
    team_iron = _team(wc_iron, team_a)
    team_pack = _team(wc_dg, team_a)
    # (code, product_idx, status, qty, qty_done, team, day_off, due_offset, process)
    # due_offset < 0 → quá hạn (cột Cần xử lý)
    mo_specs = [
        ('LSX-2026-VPS-001', 0, SxProductionOrder.STATUS_IN_PROGRESS, Decimal('400'), Decimal('185'), team_a, 0, -2, 'May thân áo'),
        ('LSX-2026-VPS-002', 1, SxProductionOrder.STATUS_RELEASED, Decimal('250'), Decimal('0'), team_cut, 1, 5, 'Trải — cắt vải theo rập'),
        ('LSX-2026-VPS-003', 2, SxProductionOrder.STATUS_DRAFT, Decimal('150'), Decimal('0'), team_print, 2, 8, 'Ép keo / dán chi tiết'),
        ('LSX-2026-VPS-004', 3, SxProductionOrder.STATUS_DONE, Decimal('300'), Decimal('300'), team_pack, 3, 2, 'Đóng gói — dán tem'),
        ('LSX-2026-VPS-005', 4, SxProductionOrder.STATUS_IN_PROGRESS, Decimal('200'), Decimal('80'), team_b, 4, -1, 'May tay — cổ — nẹp'),
        ('LSX-2026-VPS-006', 0, SxProductionOrder.STATUS_IN_PROGRESS, Decimal('220'), Decimal('40'), team_iron, 1, 4, 'Ủi định hình'),
        ('LSX-2026-VPS-007', 1, SxProductionOrder.STATUS_RELEASED, Decimal('180'), Decimal('0'), team_print, 2, 6, 'In logo / họa tiết'),
        ('LSX-2026-VPS-008', 2, SxProductionOrder.STATUS_IN_PROGRESS, Decimal('160'), Decimal('95'), team_print, 0, 3, 'Thêu logo'),
        ('LSX-2026-VPS-009', 3, SxProductionOrder.STATUS_IN_PROGRESS, Decimal('140'), Decimal('20'), team_a, 3, 7, 'QC bán thành phẩm'),
        ('LSX-2026-VPS-010', 4, SxProductionOrder.STATUS_RELEASED, Decimal('120'), Decimal('0'), team_pack, 4, 9, 'QC thành phẩm'),
    ]
    mos: list[SxProductionOrder] = []
    for code, pidx, status, qty, qty_done, team, day_off, due_off, process in mo_specs:
        pcode = product_codes[pidx % len(product_codes)]
        bom = _active_bom(pcode)
        mo, _ = SxProductionOrder.objects.update_or_create(
            code=code,
            defaults={
                'is_demo': demo,
                'product_code': pcode,
                'product_name': _product_name(pcode),
                'detail_plan': detail if day_off < 5 else None,
                'bom_version': bom,
                'qty': qty,
                'qty_done': qty_done,
                'order_date': week_start + timedelta(days=day_off),
                'due_date': today + timedelta(days=due_off),
                'planned_start': week_start + timedelta(days=day_off),
                'planned_end': week_start + timedelta(days=8 + day_off),
                'team_label': team,
                'process_name': process,
                'status': status,
                'notes': note,
                'created_by': user,
            },
        )
        mos.append(mo)
    stats['production_orders'] = len(mos)
    mo_main = mos[0]
    mo_done = mos[3]

    SxDisassemblyOrder.objects.update_or_create(
        code='LTD-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'product_code': secondary,
            'product_name': _product_name(secondary),
            'qty': Decimal('15'),
            'order_date': week_start,
            'status': 'draft',
            'notes': note,
        },
    )
    stats['disassembly_orders'] = 1

    # --- Chuỗi điều phối LSX chính ---
    mir, _ = SxMaterialIssueRequest.objects.update_or_create(
        code='YCX-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'status': 'approved',
            'request_date': week_start + timedelta(days=1),
            'notes': note,
        },
    )
    SxMaterialIssueRequestLine.objects.filter(request=mir).delete()
    for material_code, qty_req, qty_iss in [
        ('JP-VAI-COT180-WHT', Decimal('520'), Decimal('480')),
        ('JP-CHI-PES40-WHT', Decimal('400'), Decimal('380')),
    ]:
        material = resolve_existing_material(material_code)
        SxMaterialIssueRequestLine.objects.create(
            request=mir,
            material_code=material.code if material else material_code,
            material_name=material.name if material else material_code,
            qty_requested=qty_req,
            qty_issued=qty_iss,
        )
    stats['material_issues'] = 1

    SxMaterialIssueRequest.objects.update_or_create(
        code='YCX-2026-VPS-002',
        defaults={
            'is_demo': demo,
            'production_order': mos[1],
            'status': 'submitted',
            'request_date': week_start + timedelta(days=2),
            'notes': note,
        },
    )

    stat_main, _ = SxProductionStat.objects.update_or_create(
        code='TKSX-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'stat_date': today,
            'process_name': 'May thân áo',
            'qty_good': Decimal('120'),
            'qty_defect': Decimal('4'),
            'team_label': team_a,
            'status': 'confirmed',
            'notes': note,
        },
    )
    extra_stats = [
        ('TKSX-2026-VPS-002', mos[5], today, 'Ủi định hình', Decimal('65'), Decimal('1'), team_iron),
        ('TKSX-2026-VPS-003', mos[7], today, 'Thêu logo', Decimal('90'), Decimal('8'), team_print),  # lỗi cao
        ('TKSX-2026-VPS-004', mos[5], today, 'Ủi định hình', Decimal('35'), Decimal('0'), team_iron),
        ('TKSX-2026-VPS-005', mos[8], today, 'QC bán thành phẩm', Decimal('18'), Decimal('2'), team_a),
    ]
    for code, mo, sdate, proc, good, defect, team in extra_stats:
        SxProductionStat.objects.update_or_create(
            code=code,
            defaults={
                'is_demo': demo,
                'production_order': mo,
                'stat_date': sdate,
                'process_name': proc,
                'qty_good': good,
                'qty_defect': defect,
                'team_label': team,
                'status': 'confirmed',
                'notes': note,
            },
        )
    stats['production_stats'] = 1 + len(extra_stats)

    fg_main, _ = SxFgReceiptRequest.objects.update_or_create(
        code='YCNTP-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'request_date': week_start + timedelta(days=5),
            'qty': Decimal('100'),
            'status': 'submitted',
            'notes': note,
        },
    )
    SxFgReceiptRequest.objects.update_or_create(
        code='YCNTP-2026-VPS-002',
        defaults={
            'is_demo': demo,
            'production_order': mo_done,
            'request_date': week_start + timedelta(days=8),
            'qty': Decimal('300'),
            'status': 'done',
            'notes': note,
        },
    )
    stats['fg_receipts'] = 2

    SxNplSurplus.objects.update_or_create(
        code='NPLTHUA-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'material_code': 'JP-CHI-PES40-WHT',
            'material_name': 'Chỉ polyester',
            'qty': Decimal('3.2'),
            'recorded_at': week_start + timedelta(days=4),
            'notes': note,
        },
    )
    stats['npl_surplus'] = 1

    handover, _ = SxWipHandover.objects.update_or_create(
        code='BG-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'from_process': 'May thân áo',
            'to_process': 'Ủi — đóng gói',
            'qty': Decimal('115'),
            'handover_date': week_start + timedelta(days=4),
            'status': SxWipHandover.STATUS_DONE,
            'notes': note,
        },
    )
    stats['wip_handovers'] = 1

    SxWipReturn.objects.update_or_create(
        code='TRABTP-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'handover': handover,
            'production_order': mo_main,
            'qty': Decimal('6'),
            'return_date': week_start + timedelta(days=4),
            'reason': 'Lỗi đường may — sửa lại',
            'notes': note,
        },
    )
    stats['wip_returns'] = 1

    # --- QC catalog ---
    crit_group, _ = SxQcCriteriaGroup.objects.update_or_create(
        code='QCGR-VPS-MAY',
        defaults={'is_demo': demo, 'name': 'May', 'is_active': True},
    )
    crit, _ = SxQcCriteria.objects.update_or_create(
        code='QCCR-VPS-01',
        defaults={
            'is_demo': demo,
            'name': 'Đường may thẳng, không gãy chỉ',
            'group': crit_group,
            'kind': SxQcCriteria.KIND_QUALITATIVE,
            'is_active': True,
        },
    )
    SxQcCriteriaGroup.objects.update_or_create(
        code='QCGR-VPS-IN',
        defaults={'is_demo': demo, 'name': 'In / thêu', 'is_active': True},
    )

    sampling, _ = SxQcSamplingMethod.objects.update_or_create(
        code='PPMAU-VPS-10',
        defaults={
            'is_demo': demo,
            'name': 'Lấy 10 mẫu / lô',
            'method_type': 'fixed_qty',
            'sample_value': Decimal('10'),
            'is_active': True,
        },
    )
    std, _ = SxQcStandardSet.objects.update_or_create(
        code='BTKT-VPS-POLO',
        defaults={
            'is_demo': demo,
            'name': f'Tiêu chuẩn polo — {primary}',
            'product_code': primary,
            'sampling_method': sampling,
            'is_active': True,
        },
    )
    def_group, _ = SxQcDefectGroup.objects.update_or_create(
        code='QCLOI-VPS-MAY',
        defaults={'is_demo': demo, 'name': 'Lỗi may', 'is_active': True},
    )
    SxQcDefect.objects.update_or_create(
        code='QCLOI-VPS-01',
        defaults={
            'is_demo': demo,
            'name': 'Chỉ tuột / đường may lệch',
            'group': def_group,
            'severity': 'major',
            'is_active': True,
        },
    )
    stats['qc_catalog'] = 5

    qc_req, _ = SxQcRequest.objects.update_or_create(
        code='YCKT-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'product_code': primary,
            'product_name': _product_name(primary),
            'stage_name': 'QC thành phẩm',
            'qty': Decimal('120'),
            'request_date': week_start + timedelta(days=3),
            'due_date': week_start + timedelta(days=4),
            'status': 'done',
            'notes': note,
        },
    )
    SxQcInspection.objects.update_or_create(
        code='PKT-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'qc_request': qc_req,
            'standard_set': std,
            'inspected_at': week_start + timedelta(days=4),
            'qty_sample': Decimal('10'),
            'qty_pass': Decimal('9'),
            'qty_fail': Decimal('1'),
            'result': SxQcInspection.RESULT_PASS,
            'status': 'done',
            'notes': note,
        },
    )
    stats['qc_requests'] = 1

    # --- Đóng gói / GC / giao việc / dừng chuyền / NCR ---
    SxPackingRecord.objects.update_or_create(
        code='DG-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'fg_receipt': fg_main,
            'pack_date': week_start + timedelta(days=5),
            'qty': Decimal('95'),
            'carton_count': 4,
            'lot_code': f'LOT-VPS-{week_start:%Y%m}',
            'status': SxPackingRecord.STATUS_CONFIRMED,
            'notes': note,
        },
    )
    SxPackingRecord.objects.update_or_create(
        code='DG-2026-VPS-002',
        defaults={
            'is_demo': demo,
            'production_order': mo_done,
            'pack_date': week_start + timedelta(days=9),
            'qty': Decimal('280'),
            'carton_count': 12,
            'lot_code': f'LOT-VPS-DONE-{week_start:%Y%m}',
            'status': SxPackingRecord.STATUS_CONFIRMED,
            'notes': note,
        },
    )
    stats['packing'] = 2

    SxSubcontractOrder.objects.update_or_create(
        code='GC-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'vendor_name': 'Xưởng in thêu Minh Phát',
            'product_code': primary,
            'product_name': _product_name(primary),
            'process_name': 'In / thêu logo',
            'qty': Decimal('400'),
            'order_date': week_start,
            'due_date': week_start + timedelta(days=7),
            'status': SxSubcontractOrder.STATUS_SENT,
            'notes': note,
        },
    )
    SxSubcontractOrder.objects.update_or_create(
        code='GC-2026-VPS-002',
        defaults={
            'is_demo': demo,
            'vendor_name': 'Gia công May Bình Dương',
            'product_code': secondary,
            'product_name': _product_name(secondary),
            'process_name': 'May thân',
            'qty': Decimal('200'),
            'order_date': week_start + timedelta(days=2),
            'status': 'draft',
            'notes': note,
        },
    )
    stats['subcontract'] = 2

    for idx, (mo, wc, title) in enumerate([
        (mo_main, wc_may1, 'May thân áo — lô 1'),
        (mos[3], wc_dg, 'Đóng gói xuất kho'),
        (mos[1], wc_cut, 'Trải — cắt theo rập'),
        (mos[4], wc_may2, 'May thân — lô 2'),
    ]):
        SxWorkAssignment.objects.update_or_create(
            code=f'GV-2026-VPS-{idx + 1:02d}',
            defaults={
                'is_demo': demo,
                'production_order': mo,
                'work_center': wc,
                'process_name': wc.team_label,
                'title': title,
                'assignee_label': wc.team_label,
                'due_date': week_start + timedelta(days=3 + idx),
                'status': SxWorkAssignment.STATUS_OPEN if idx < 3 else SxWorkAssignment.STATUS_DONE,
                'notes': note,
            },
        )
    stats['work_assignments'] = 4

    for idx, (mo, wc, mins, reason) in enumerate([
        (mo_main, wc_may1, 75, 'Máy may hỏng kim — chờ bảo trì'),
        (mo_main, wc_may1, 30, 'Thiếu chỉ tạm thời'),
        (mos[4], wc_may2, 90, 'Chờ NVL từ kho / dừng chuyền'),
    ]):
        SxDowntimeEvent.objects.update_or_create(
            code=f'DC-2026-VPS-{idx + 1:02d}',
            defaults={
                'is_demo': demo,
                'production_order': mo,
                'work_center': wc,
                'team_label': (wc.team_label or wc.name) if wc else '',
                'event_date': today,
                'minutes': mins,
                'reason': reason,
                'notes': note,
            },
        )
    stats['downtime'] = 3

    SxQcAlert.objects.update_or_create(
        code='CBQC-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'alert_type': SxQcAlert.TYPE_DEFECT_RATE,
            'production_order': mos[7],
            'production_stat': SxProductionStat.objects.filter(code='TKSX-2026-VPS-003').first(),
            'process_name': 'Thêu logo',
            'defect_rate': Decimal('8.2'),
            'tolerance_limit': Decimal('5'),
            'qty_good': Decimal('90'),
            'qty_defect': Decimal('8'),
            'message': f'Tỷ lệ lỗi thêu vượt ngưỡng — tổ {team_b}',
            'status': SxQcAlert.STATUS_OPEN,
        },
    )
    SxQcAlert.objects.update_or_create(
        code='CBQC-2026-VPS-002',
        defaults={
            'is_demo': demo,
            'alert_type': SxQcAlert.TYPE_QC_FAIL,
            'production_order': mo_main,
            'process_name': 'QC thành phẩm',
            'defect_rate': Decimal('6.0'),
            'tolerance_limit': Decimal('5'),
            'qty_good': Decimal('112'),
            'qty_defect': Decimal('8'),
            'message': f'Phiếu QC không đạt — tổ {team_a}',
            'status': SxQcAlert.STATUS_OPEN,
        },
    )
    stats['qc_alerts'] = 2

    SxNcrCase.objects.update_or_create(
        code='NCR-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'production_order': mo_main,
            'disposition': SxNcrCase.DISP_REWORK,
            'qty': Decimal('4'),
            'process_name': 'May thân áo',
            'status': SxNcrCase.STATUS_CONFIRMED,
            'rework_stat': stat_main,
            'notes': note,
        },
    )
    stats['ncr'] = 1

    # --- Giá thành kế hoạch ---
    sheet, _ = SxStandardCostSheet.objects.update_or_create(
        code='GTDM-2026-Q3-VPS',
        defaults={
            'is_demo': demo,
            'name': 'Giá thành định mức Q3/2026',
            'date_from': week_start,
            'date_to': week_end,
            'status': 'confirmed',
            'notes': note,
        },
    )
    SxStandardCostLine.objects.filter(sheet=sheet).delete()
    for code in product_codes[:6]:
        bom_v = _active_bom(code)
        if bom_v:
            result = compute_costing(bom_v)
            SxStandardCostLine.objects.create(
                sheet=sheet,
                product_code=code,
                product_name=_product_name(code),
                unit_cost=result.total_cost,
                material_cost=result.material_cost,
                labor_cost=result.labor_cost,
                overhead_cost=result.overhead_cost,
            )
    stats['standard_cost_sheets'] = 1

    order_cost, _ = SxOrderPlanCost.objects.update_or_create(
        code='GTDH-2026-VPS-001',
        defaults={
            'is_demo': demo,
            'name': 'GTKH đơn mẫu',
            'kv_order_code': 'DH-MAU-2026',
            'date_from': week_start,
            'date_to': week_end,
            'total_cost': Decimal('0'),
            'status': 'confirmed',
            'notes': note,
        },
    )
    SxOrderPlanCostLine.objects.filter(sheet=order_cost).delete()
    total = Decimal('0')
    for code in product_codes[:4]:
        bom_v = _active_bom(code)
        unit = compute_costing(bom_v).total_cost if bom_v else Decimal('68000')
        qty = Decimal('180')
        line_cost = (unit * qty).quantize(Decimal('0.01'))
        total += line_cost
        SxOrderPlanCostLine.objects.create(
            sheet=order_cost,
            product_code=code,
            product_name=_product_name(code),
            qty=qty,
            unit_cost=unit,
            line_cost=line_cost,
        )
    order_cost.total_cost = total
    order_cost.save(update_fields=['total_cost'])
    stats['order_plan_costs'] = 1

    _ = crit
    return stats


@transaction.atomic
def seed_vps_demo(
    *,
    product_codes: list[str],
    user=None,
    visible: bool = True,
    activate_bom: bool = True,
    costing: bool = True,
    force_lines: bool = False,
) -> dict:
    """Seed hồ sơ + hub đầy đủ cho VPS."""
    doc_stats = {'created': 0, 'updated': 0, 'skipped': 0}
    for code in product_codes:
        try:
            doc, _bom, stats = seed_demo_tech_doc(
                code,
                user=user,
                activate=activate_bom,
                costing=costing,
                force_lines=force_lines,
                adopt_existing=True,
            )
            if visible:
                doc.notes = f'{VPS_DEMO_NOTE} Hồ sơ sportswear — {doc.product_name or code}'
                doc.save(update_fields=['notes', 'updated_at'])
            if stats['created']:
                doc_stats['created'] += 1
            else:
                doc_stats['updated'] += 1
        except Exception:
            doc_stats['skipped'] += 1

    hub_stats = seed_vps_hub(product_codes=product_codes, user=user, visible=visible)
    return {'docs': doc_stats, 'hub': hub_stats}
