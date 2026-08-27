"""Seed dữ liệu demo hub: kế hoạch / điều phối / QC / giá thành KH."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxDetailPlan,
    SxDetailPlanLine,
    SxDisassemblyOrder,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxMaterialIssueRequestLine,
    SxMaterialPlan,
    SxMaterialPlanLine,
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxNplSurplus,
    SxOrderPlanCost,
    SxOrderPlanCostLine,
    SxOverallPlan,
    SxOverallPlanLine,
    SxProductionOrder,
    SxProductionStat,
    SxPurchaseOrder,
    SxPurchaseOrderLine,
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
    SxWipHandover,
    SxWipReturn,
)
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.costing import compute_costing
from san_xuat.services.demo_seed import DEMO_NOTE_PREFIX, resolve_existing_material

HUB_DEMO_MODELS_DELETE_ORDER = (
    SxWipReturn,
    SxWipHandover,
    SxNplSurplus,
    SxFgReceiptRequest,
    SxProductionStat,
    SxMaterialIssueRequest,
    SxQcInspection,
    SxQcRequest,
    SxDisassemblyOrder,
    SxProductionOrder,
    SxPurchaseOrder,
    SxNplPurchaseRequest,
    SxMaterialPlan,
    SxDetailPlan,
    SxOverallPlan,
    SxOrderPlanCost,
    SxStandardCostSheet,
    SxQcDefect,
    SxQcCriteria,
    SxQcStandardSet,
    SxQcSamplingMethod,
    SxQcDefectGroup,
    SxQcCriteriaGroup,
)


@transaction.atomic
def clear_demo_hub() -> int:
    total = 0
    for model in HUB_DEMO_MODELS_DELETE_ORDER:
        deleted, _ = model.objects.filter(is_demo=True).delete()
        total += deleted
    return total


def _product_name(code: str) -> str:
    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    return doc.product_name if doc else ''


def _active_bom(code: str) -> BomVersion | None:
    doc = ProductTechDoc.objects.filter(product_code__iexact=code).first()
    if not doc:
        return None
    return doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE).first()


@transaction.atomic
def seed_demo_hub(*, product_codes: list[str], user=None) -> dict:
    """Tạo chuỗi demo cho mọi menu hub (trừ kho SP/NPL)."""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=13)
    stats: dict[str, int] = {}

    primary = product_codes[0] if product_codes else 'SP008073'
    primary_name = _product_name(primary) or primary

    overall, _ = SxOverallPlan.objects.update_or_create(
        code='KHTT-DEMO-2026Q3',
        defaults={
            'is_demo': True,
            'name': 'Kế hoạch SX Q3/2026 (demo)',
            'date_from': week_start,
            'date_to': week_end,
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['overall_plans'] = 1
    SxOverallPlanLine.objects.filter(plan=overall).delete()
    for idx, code in enumerate(product_codes[:4]):
        SxOverallPlanLine.objects.create(
            plan=overall,
            product_code=code,
            product_name=_product_name(code),
            qty_required=Decimal('500') + idx * 100,
            qty_planned=Decimal('400') + idx * 80,
            capacity_per_day=Decimal('80'),
        )

    detail, _ = SxDetailPlan.objects.update_or_create(
        code='KHCT-DEMO-2026Q3',
        defaults={
            'is_demo': True,
            'name': 'KH chi tiết 2 tuần (demo)',
            'overall_plan': overall,
            'date_from': week_start,
            'date_to': week_start + timedelta(days=6),
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['detail_plans'] = 1
    SxDetailPlanLine.objects.filter(plan=detail).delete()
    for day in range(5):
        code = product_codes[day % len(product_codes)] if product_codes else primary
        SxDetailPlanLine.objects.create(
            plan=detail,
            plan_date=week_start + timedelta(days=day),
            product_code=code,
            product_name=_product_name(code),
            qty=Decimal('80'),
        )

    mat_plan, _ = SxMaterialPlan.objects.update_or_create(
        code='KHNVL-DEMO-2026Q3',
        defaults={
            'is_demo': True,
            'name': 'Nhu cầu NPL theo KHTT (demo)',
            'overall_plan': overall,
            'status': SxOverallPlan.STATUS_CONFIRMED,
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['material_plans'] = 1
    SxMaterialPlanLine.objects.filter(plan=mat_plan).delete()
    for material_code, _qty, _scrap, _sort in [
        ('JP-VAI-COT180-WHT', Decimal('1.2'), Decimal('5'), 10),
        ('JP-CHI-PES40-WHT', Decimal('1'), Decimal('0'), 20),
    ]:
        material = resolve_existing_material(material_code)
        SxMaterialPlanLine.objects.create(
            plan=mat_plan,
            material_code=material.code if material else material_code,
            material_name=material.name if material else material_code,
            qty_required=Decimal('480'),
            qty_on_hand=Decimal('120'),
            qty_shortfall=Decimal('360'),
        )

    pr, _ = SxNplPurchaseRequest.objects.update_or_create(
        code='YCM-DEMO-001',
        defaults={
            'is_demo': True,
            'material_plan': mat_plan,
            'due_date': week_start + timedelta(days=7),
            'status': 'approved',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['npl_prs'] = 1
    SxNplPurchaseRequestLine.objects.filter(request=pr).delete()
    SxNplPurchaseRequestLine.objects.create(
        request=pr,
        material_code='JP-VAI-COT180-WHT',
        material_name='Vải cotton trắng',
        qty=Decimal('360'),
    )

    po, _ = SxPurchaseOrder.objects.update_or_create(
        code='DMH-DEMO-001',
        defaults={
            'is_demo': True,
            'supplier_name': 'NCC Vải Đồng Nai (demo)',
            'purchase_request': pr,
            'status': 'confirmed',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['purchase_orders'] = 1
    SxPurchaseOrderLine.objects.filter(order=po).delete()
    SxPurchaseOrderLine.objects.create(
        order=po,
        material_code='JP-VAI-COT180-WHT',
        material_name='Vải cotton trắng',
        qty_ordered=Decimal('360'),
        qty_received=Decimal('0'),
    )

    bom = _active_bom(primary)
    mo, _ = SxProductionOrder.objects.update_or_create(
        code='LSX-DEMO-001',
        defaults={
            'is_demo': True,
            'product_code': primary,
            'product_name': primary_name,
            'detail_plan': detail,
            'bom_version': bom,
            'qty': Decimal('400'),
            'qty_done': Decimal('120'),
            'order_date': week_start,
            'due_date': week_start + timedelta(days=10),
            'planned_start': week_start + timedelta(days=1),
            'planned_end': week_start + timedelta(days=8),
            'team_label': 'Tổ May 1',
            'status': SxProductionOrder.STATUS_IN_PROGRESS,
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['production_orders'] = 1

    SxDisassemblyOrder.objects.update_or_create(
        code='LTD-DEMO-001',
        defaults={
            'is_demo': True,
            'product_code': product_codes[1] if len(product_codes) > 1 else primary,
            'product_name': _product_name(product_codes[1] if len(product_codes) > 1 else primary),
            'qty': Decimal('20'),
            'order_date': week_start,
            'status': 'draft',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['disassembly_orders'] = 1

    mir, _ = SxMaterialIssueRequest.objects.update_or_create(
        code='YCX-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'status': 'approved',
            'request_date': week_start + timedelta(days=1),
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['material_issues'] = 1
    SxMaterialIssueRequestLine.objects.filter(request=mir).delete()
    SxMaterialIssueRequestLine.objects.create(
        request=mir,
        material_code='JP-VAI-COT180-WHT',
        material_name='Vải cotton trắng',
        qty_requested=Decimal('480'),
        qty_issued=Decimal('400'),
    )

    SxProductionStat.objects.update_or_create(
        code='TKSX-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'stat_date': week_start + timedelta(days=3),
            'process_name': 'May thân áo',
            'qty_good': Decimal('100'),
            'qty_defect': Decimal('3'),
            'team_label': 'Tổ May 1',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['production_stats'] = 1

    SxFgReceiptRequest.objects.update_or_create(
        code='YCNTP-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'request_date': week_start + timedelta(days=5),
            'qty': Decimal('100'),
            'status': 'submitted',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['fg_receipts'] = 1

    SxNplSurplus.objects.update_or_create(
        code='NPLTHUA-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'material_code': 'JP-CHI-PES40-WHT',
            'material_name': 'Chỉ polyester',
            'qty': Decimal('2.5'),
            'recorded_at': week_start + timedelta(days=4),
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['npl_surplus'] = 1

    handover, _ = SxWipHandover.objects.update_or_create(
        code='BG-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'from_process': 'May thân áo',
            'to_process': 'Ủi — đóng gói',
            'qty': Decimal('95'),
            'handover_date': week_start + timedelta(days=4),
            'status': SxWipHandover.STATUS_DONE,
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['wip_handovers'] = 1

    SxWipReturn.objects.update_or_create(
        code='TRABTP-DEMO-001',
        defaults={
            'is_demo': True,
            'handover': handover,
            'production_order': mo,
            'qty': Decimal('5'),
            'return_date': week_start + timedelta(days=4),
            'reason': 'Lỗi đường may — sửa lại',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['wip_returns'] = 1

    crit_group, _ = SxQcCriteriaGroup.objects.update_or_create(
        code='QCGR-DEMO-MAY',
        defaults={'is_demo': True, 'name': 'May — demo', 'is_active': True},
    )
    crit, _ = SxQcCriteria.objects.update_or_create(
        code='QCCR-DEMO-01',
        defaults={
            'is_demo': True,
            'name': 'Đường may thẳng, không gãy chỉ',
            'group': crit_group,
            'kind': SxQcCriteria.KIND_QUALITATIVE,
            'team_slug': 'may',
            'is_active': True,
        },
    )
    stats['qc_criteria'] = 1

    SxQcCriteriaGroup.objects.update_or_create(
        code='QCGR-DEMO-IN',
        defaults={'is_demo': True, 'name': 'In / thêu — demo', 'is_active': True},
    )

    sampling, _ = SxQcSamplingMethod.objects.update_or_create(
        code='PPMAU-DEMO-10',
        defaults={
            'is_demo': True,
            'name': 'Lấy 10 mẫu / lô (demo)',
            'method_type': 'fixed_qty',
            'sample_value': Decimal('10'),
            'is_active': True,
        },
    )
    stats['qc_sampling'] = 1

    std, _ = SxQcStandardSet.objects.update_or_create(
        code='BTKT-DEMO-POLO',
        defaults={
            'is_demo': True,
            'name': f'Tiêu chuẩn polo — {primary}',
            'product_code': primary,
            'sampling_method': sampling,
            'is_active': True,
        },
    )
    stats['qc_standards'] = 1

    def_group, _ = SxQcDefectGroup.objects.update_or_create(
        code='QCLOI-DEMO-MAY',
        defaults={'is_demo': True, 'name': 'Lỗi may — demo', 'is_active': True},
    )
    SxQcDefect.objects.update_or_create(
        code='QCLOI-DEMO-01',
        defaults={
            'is_demo': True,
            'name': 'Chỉ tuột / đường may lệch',
            'group': def_group,
            'severity': 'major',
            'is_active': True,
        },
    )
    stats['qc_defects'] = 1

    qc_req, _ = SxQcRequest.objects.update_or_create(
        code='YCKT-DEMO-001',
        defaults={
            'is_demo': True,
            'production_order': mo,
            'product_code': primary,
            'product_name': primary_name,
            'stage_name': 'QC thành phẩm',
            'qty': Decimal('100'),
            'request_date': week_start + timedelta(days=3),
            'due_date': week_start + timedelta(days=4),
            'status': 'done',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['qc_requests'] = 1

    SxQcInspection.objects.update_or_create(
        code='PKT-DEMO-001',
        defaults={
            'is_demo': True,
            'qc_request': qc_req,
            'standard_set': std,
            'inspected_at': week_start + timedelta(days=4),
            'qty_sample': Decimal('10'),
            'qty_pass': Decimal('9'),
            'qty_fail': Decimal('1'),
            'result': SxQcInspection.RESULT_PASS,
            'status': 'done',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['qc_inspections'] = 1

    sheet, _ = SxStandardCostSheet.objects.update_or_create(
        code='GTDM-DEMO-2026Q3',
        defaults={
            'is_demo': True,
            'name': 'Giá thành định mức Q3 (demo)',
            'date_from': week_start,
            'date_to': week_end,
            'status': 'confirmed',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['standard_cost_sheets'] = 1
    SxStandardCostLine.objects.filter(sheet=sheet).delete()
    for code in product_codes[:4]:
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

    order_cost, _ = SxOrderPlanCost.objects.update_or_create(
        code='GTDH-DEMO-001',
        defaults={
            'is_demo': True,
            'name': 'GTKH đơn KV mẫu (demo)',
            'kv_order_code': 'DH-DEMO-KV',
            'date_from': week_start,
            'date_to': week_end,
            'total_cost': Decimal('0'),
            'status': 'confirmed',
            'notes': DEMO_NOTE_PREFIX,
        },
    )
    stats['order_plan_costs'] = 1
    SxOrderPlanCostLine.objects.filter(sheet=order_cost).delete()
    total = Decimal('0')
    for code in product_codes[:3]:
        bom_v = _active_bom(code)
        unit = compute_costing(bom_v).total_cost if bom_v else Decimal('65000')
        qty = Decimal('200')
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

    stats['qc_criteria_groups'] = SxQcCriteriaGroup.objects.filter(is_demo=True).count()
    _ = crit  # used
    return stats
