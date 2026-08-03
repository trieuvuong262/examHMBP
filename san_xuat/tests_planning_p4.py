"""Test P4 — đóng vòng phản hồi kế hoạch sản xuất.

Phủ 6 hạng mục:
  1. KHNVL theo thời điểm (need_date) → YCM → DMH.
  2. DMH → phiếu nhập kho NPL + đồng bộ SL đã nhập.
  3. Nhắc việc sản xuất trên trang chủ (lệnh trễ, NPL chưa về).
  4. OEE đầy đủ (Sẵn sàng × Hiệu suất × Chất lượng).
  5. Nhật ký kế hoạch.
  6. Lấy mẫu AQL theo ISO 2859-1.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_POSTED
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockReceipt,
    StockReceiptLine,
    Supplier,
    Unit,
    WarehouseLocation,
)

from san_xuat.hub_models import (
    SxDetailPlan,
    SxNplPurchaseRequest,
    SxOverallPlan,
    SxPlanAuditLog,
    SxProductionOrder,
    SxProductionStat,
    SxPurchaseOrder,
    SxQcSamplingMethod,
    SxWorkCenter,
)
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.planning import (
    PlanningError,
    add_overall_plan_line,
    approve_npl_purchase_request,
    build_po_from_purchase_request,
    build_pr_from_material_plan,
    confirm_material_plan,
    confirm_overall_plan,
    confirm_purchase_order,
    create_overall_plan,
    explode_detail_plan_from_overall,
    explode_material_plan,
    submit_npl_purchase_request,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _material(code, name='NPL test', price='10000'):
    cat, _ = MaterialCategory.objects.get_or_create(code='CAT-P4', defaults={'name': 'Nhóm P4'})
    unit, _ = Unit.objects.get_or_create(code='M', defaults={'name': 'Mét'})
    return Material.objects.create(
        code=code, name=name, category=cat, unit=unit, base_price=Decimal(price),
    )


def _product_with_bom(code, materials, *, steps=None):
    """materials = [(Material, qty)]; steps = [(name, work_center, minutes)]"""
    doc = ProductTechDoc.objects.create(
        product_code=code, product_name=f'SP {code}', is_active=True,
    )
    bom = BomVersion.objects.create(
        tech_doc=doc, version_label='v1', status=BomVersion.STATUS_ACTIVE,
    )
    for idx, (material, qty) in enumerate(materials):
        BomLine.objects.create(bom=bom, material=material, qty=Decimal(str(qty)), sort_order=idx)
    for i, (name, wc, minutes) in enumerate(steps or [], start=1):
        smv = Decimal(str(minutes))
        ProcessStep.objects.create(
            bom=bom,
            sequence=i * 10,
            process_name=name,
            work_center=wc,
            norm_per_hour=(Decimal('60') / smv) if smv > 0 else Decimal('1'),
            std_time_minutes=smv,
        )
    return doc, bom


def _center(code, name, heads=10, *, minutes=480, eff='100'):
    return SxWorkCenter.objects.create(
        code=code,
        name=name,
        team_label=name,
        headcount=heads,
        shift_minutes_per_head=minutes,
        efficiency_pct=Decimal(eff),
        capacity_per_day=Decimal('0'),
    )


def _director(username):
    from django.contrib.auth.models import User

    from hrm.models import Profile
    from hrm.permissions import ROLE_DIRECTOR

    user = User.objects.create_user(username, f'{username}@test.local', 'x')
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.role = ROLE_DIRECTOR
    profile.save()
    user.refresh_from_db()
    return user


# ---------------------------------------------------------------------------
# 1. KHNVL theo thời điểm
# ---------------------------------------------------------------------------

class MaterialNeedDateTests(TestCase):
    def setUp(self):
        self.mat = _material('VAI-P4')
        _product_with_bom('SP-P4', [(self.mat, '2')])
        self.overall = create_overall_plan(
            name='KHTT P4', date_from=date(2026, 9, 1), date_to=date(2026, 9, 7),
        )
        add_overall_plan_line(
            plan_id=self.overall.pk, product_code='SP-P4', qty_planned=Decimal('100'),
        )
        confirm_overall_plan(plan_id=self.overall.pk)

    def test_need_date_uses_detail_plan_minus_prep_days(self):
        explode_detail_plan_from_overall(overall_plan_id=self.overall.pk)
        plan = explode_material_plan(overall_plan_id=self.overall.pk)
        line = plan.lines.first()
        self.assertIsNotNone(line.need_date)
        # KHCT bắt đầu 01/09; mặc định chuẩn bị trước 2 ngày
        self.assertEqual(line.need_date, date(2026, 8, 30))

    def test_need_date_falls_back_to_plan_start_without_detail_plan(self):
        plan = explode_material_plan(overall_plan_id=self.overall.pk)
        self.assertEqual(plan.lines.first().need_date, date(2026, 8, 30))

    def test_prep_days_setting_is_respected(self):
        from san_xuat.hub_models import SxGeneralSettings

        cfg = SxGeneralSettings.load()
        cfg.npl_prep_days = 7
        cfg.save(update_fields=['npl_prep_days'])
        plan = explode_material_plan(overall_plan_id=self.overall.pk)
        self.assertEqual(plan.lines.first().need_date, date(2026, 8, 25))

    def test_pr_due_date_from_earliest_need_date(self):
        plan = explode_material_plan(overall_plan_id=self.overall.pk)
        confirm_material_plan(plan_id=plan.pk)
        pr = build_pr_from_material_plan(material_plan_id=plan.pk)
        self.assertEqual(pr.due_date, date(2026, 8, 30))
        self.assertEqual(pr.lines.first().need_date, date(2026, 8, 30))

    def test_po_carries_need_date_and_price(self):
        plan = explode_material_plan(overall_plan_id=self.overall.pk)
        confirm_material_plan(plan_id=plan.pk)
        pr = build_pr_from_material_plan(material_plan_id=plan.pk)
        submit_npl_purchase_request(request_id=pr.pk)
        approve_npl_purchase_request(request_id=pr.pk)
        po = build_po_from_purchase_request(purchase_request_id=pr.pk, supplier_name='NCC A')
        line = po.lines.first()
        self.assertEqual(line.need_date, date(2026, 8, 30))
        self.assertEqual(line.unit_price, Decimal('10000.00'))
        self.assertEqual(po.expected_date, date(2026, 8, 30))


# ---------------------------------------------------------------------------
# 2. DMH → phiếu nhập kho NPL
# ---------------------------------------------------------------------------

class PurchaseOrderReceiptTests(TestCase):
    def setUp(self):
        from san_xuat.services import po_receipt

        self.po_receipt = po_receipt
        self.mat = _material('VAI-RECV')
        self.location = WarehouseLocation.objects.create(
            code='KHO-1', name='Kho chính', location_kind=WarehouseLocation.KIND_STOCK,
        )
        self.supplier = Supplier.objects.create(code='NCC1', name='Nhà cung cấp 1')
        self.po = SxPurchaseOrder.objects.create(
            code='DMH-P4-1',
            supplier=self.supplier,
            supplier_name=self.supplier.name,
            status=SxPurchaseOrder.STATUS_CONFIRMED,
            expected_date=date(2026, 9, 1),
        )
        self.po.lines.create(
            material_code='VAI-RECV',
            material_name='NPL test',
            qty_ordered=Decimal('100'),
            unit_price=Decimal('12000'),
        )

    def test_draft_po_cannot_create_receipt(self):
        self.po.status = SxPurchaseOrder.STATUS_DRAFT
        self.po.save(update_fields=['status'])
        with self.assertRaises(PlanningError):
            self.po_receipt.create_receipt_from_po(order_id=self.po.pk)

    def test_unknown_material_is_reported(self):
        self.po.lines.create(material_code='KHONG-CO', qty_ordered=Decimal('5'))
        with self.assertRaises(PlanningError) as ctx:
            self.po_receipt.create_receipt_from_po(order_id=self.po.pk)
        self.assertIn('KHONG-CO', str(ctx.exception))

    def test_creates_draft_receipt_with_lines(self):
        receipt = self.po_receipt.create_receipt_from_po(order_id=self.po.pk)
        self.assertEqual(receipt.po_number, 'DMH-P4-1')
        self.assertEqual(receipt.supplier, self.supplier)
        line = receipt.lines.first()
        self.assertEqual(line.received_qty, Decimal('100.000'))
        self.assertEqual(line.unit_price, Decimal('12000.00'))
        self.assertEqual(line.batch_code, 'DMH-P4-1')
        self.po.refresh_from_db()
        self.assertEqual(self.po.stock_receipt_id, receipt.pk)

    def test_second_receipt_blocked_while_draft(self):
        self.po_receipt.create_receipt_from_po(order_id=self.po.pk)
        with self.assertRaises(PlanningError):
            self.po_receipt.create_receipt_from_po(order_id=self.po.pk)

    def test_sync_updates_qty_and_status_after_posting(self):
        receipt = self.po_receipt.create_receipt_from_po(order_id=self.po.pk)
        receipt.status = DOC_STATUS_POSTED
        receipt.save(update_fields=['status'])

        result = self.po_receipt.sync_po_received_from_po_receipts(order_id=self.po.pk)
        self.assertEqual(result['updated'], 1)
        self.assertTrue(result['received_full'])
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, SxPurchaseOrder.STATUS_RECEIVED)
        self.assertEqual(self.po.lines.first().qty_received, Decimal('100.0000'))

    def test_sync_partial_keeps_confirmed(self):
        receipt = StockReceipt.objects.create(
            number='PN-P4-9', receipt_date=timezone.localdate(), po_number=self.po.code,
            status=DOC_STATUS_POSTED,
        )
        StockReceiptLine.objects.create(
            receipt=receipt, material=self.mat, received_qty=Decimal('40'),
            location=self.location, unit_price=Decimal('12000'),
        )
        result = self.po_receipt.sync_po_received_from_po_receipts(order_id=self.po.pk)
        self.assertFalse(result['received_full'])
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, SxPurchaseOrder.STATUS_CONFIRMED)
        self.assertEqual(self.po.lines.first().qty_received, Decimal('40.0000'))

    def test_no_remaining_qty_raises(self):
        line = self.po.lines.first()
        line.qty_received = line.qty_ordered
        line.save(update_fields=['qty_received'])
        with self.assertRaises(PlanningError):
            self.po_receipt.create_receipt_from_po(order_id=self.po.pk)


# ---------------------------------------------------------------------------
# 3. Nhắc việc sản xuất ở trang chủ
# ---------------------------------------------------------------------------

class ProductionWidgetTests(TestCase):
    def setUp(self):
        self.user = _director('p4widget')
        self.today = timezone.localdate()

    def _widgets(self):
        from assessment.portal_widgets import _san_xuat_widgets

        return _san_xuat_widgets(self.user)

    def test_late_mo_creates_widget(self):
        SxProductionOrder.objects.create(
            code='LSX-LATE-1',
            product_code='SP-X',
            qty=Decimal('100'),
            qty_done=Decimal('10'),
            order_date=self.today - timedelta(days=10),
            due_date=self.today - timedelta(days=1),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        titles = [w['title'] for w in self._widgets()]
        self.assertIn('Lệnh sản xuất trễ hạn', titles)

    def test_finished_mo_is_not_late(self):
        SxProductionOrder.objects.create(
            code='LSX-DONE-1',
            product_code='SP-X',
            qty=Decimal('100'),
            qty_done=Decimal('100'),
            order_date=self.today - timedelta(days=10),
            due_date=self.today - timedelta(days=1),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        self.assertEqual(self._widgets(), [])

    def test_upcoming_mo_creates_soft_widget(self):
        SxProductionOrder.objects.create(
            code='LSX-SOON-1',
            product_code='SP-X',
            qty=Decimal('50'),
            qty_done=Decimal('0'),
            order_date=self.today,
            due_date=self.today + timedelta(days=1),
            status=SxProductionOrder.STATUS_RELEASED,
        )
        titles = [w['title'] for w in self._widgets()]
        self.assertIn('Lệnh sản xuất sắp tới hạn', titles)

    def test_overdue_purchase_order_creates_widget(self):
        po = SxPurchaseOrder.objects.create(
            code='DMH-LATE-1',
            status=SxPurchaseOrder.STATUS_CONFIRMED,
            expected_date=self.today - timedelta(days=2),
        )
        po.lines.create(material_code='VAI-Z', qty_ordered=Decimal('80'))
        titles = [w['title'] for w in self._widgets()]
        self.assertIn('Nguyên phụ liệu chưa về', titles)


# ---------------------------------------------------------------------------
# 4. OEE đầy đủ
# ---------------------------------------------------------------------------

class OeeTests(TestCase):
    def setUp(self):
        from san_xuat.hub_models import SxDowntimeEvent

        self.downtime_model = SxDowntimeEvent
        self.sew = _center('T-OEE', 'May OEE', heads=1, minutes=480, eff='100')
        _product_with_bom('SP-OEE', [], steps=[('May', self.sew, '10')])
        self.mo = SxProductionOrder.objects.create(
            code='LSX-OEE-1',
            product_code='SP-OEE',
            qty=Decimal('100'),
            order_date=date(2026, 9, 1),
            team_label='May OEE',
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )

    def _stat(self, good, defect, process='May'):
        return SxProductionStat.objects.create(
            code=f'TKSX-OEE-{good}-{defect}',
            production_order=self.mo,
            stat_date=date(2026, 9, 1),
            process_name=process,
            qty_good=Decimal(str(good)),
            qty_defect=Decimal(str(defect)),
            team_label='May OEE',
            status=SxProductionStat.STATUS_CONFIRMED,
        )

    def _rows(self):
        from san_xuat.services.oee import build_oee_rows

        return build_oee_rows(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1))

    def test_availability_reflects_downtime(self):
        self.downtime_model.objects.create(
            code='DT-OEE-1', work_center=self.sew, event_date=date(2026, 9, 1),
            reason='Máy hỏng', minutes=48,
        )
        row = self._rows()['rows'][0]
        self.assertEqual(row.planned_minutes, Decimal('480.00'))
        self.assertEqual(row.operating_minutes, Decimal('432.00'))
        self.assertEqual(row.availability_pct, Decimal('90.0'))

    def test_performance_from_smv(self):
        self._stat(40, 0)  # 40 cái × 10 phút = 400 phút định mức / 480 phút
        row = self._rows()['rows'][0]
        self.assertEqual(row.earned_minutes, Decimal('400.00'))
        self.assertEqual(row.performance_pct, Decimal('83.3'))

    def test_quality_and_oee_product(self):
        self._stat(45, 5)  # 50 cái × 10 = 500 phút, chất lượng 90%
        row = self._rows()['rows'][0]
        self.assertEqual(row.quality_pct, Decimal('90.0'))
        self.assertEqual(row.availability_pct, Decimal('100.0'))
        # 100% × 104.2% × 90% ≈ 93.8%
        self.assertGreater(row.oee_pct, Decimal('90'))

    def test_stat_without_smv_flagged(self):
        _product_with_bom('SP-NOSMV', [])
        mo = SxProductionOrder.objects.create(
            code='LSX-NOSMV', product_code='SP-NOSMV', qty=Decimal('10'),
            order_date=date(2026, 9, 1), team_label='May OEE',
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        SxProductionStat.objects.create(
            code='TKSX-NOSMV', production_order=mo, stat_date=date(2026, 9, 1),
            process_name='Không rõ', qty_good=Decimal('10'), team_label='May OEE',
            status=SxProductionStat.STATUS_CONFIRMED,
        )
        row = self._rows()['rows'][0]
        self.assertEqual(row.qty_no_smv, Decimal('10.00'))

    def test_draft_stat_ignored(self):
        SxProductionStat.objects.create(
            code='TKSX-DRAFT', production_order=self.mo, stat_date=date(2026, 9, 1),
            process_name='May', qty_good=Decimal('99'), team_label='May OEE',
            status=SxProductionStat.STATUS_DRAFT,
        )
        row = self._rows()['rows'][0]
        self.assertEqual(row.qty_good, Decimal('0'))


# ---------------------------------------------------------------------------
# 5. Nhật ký kế hoạch
# ---------------------------------------------------------------------------

class PlanAuditLogTests(TestCase):
    def setUp(self):
        self.user = _director('p4audit')
        self.overall = create_overall_plan(
            name='KH audit', date_from=date(2026, 9, 1), date_to=date(2026, 9, 5),
        )
        add_overall_plan_line(
            plan_id=self.overall.pk, product_code='SP-AUDIT', qty_planned=Decimal('50'),
        )

    def test_confirm_writes_log_with_user(self):
        confirm_overall_plan(plan_id=self.overall.pk, user=self.user)
        log = SxPlanAuditLog.objects.filter(object_type='SxOverallPlan').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, SxPlanAuditLog.ACTION_CONFIRM)
        self.assertEqual(log.object_code, self.overall.code)
        self.assertEqual(log.username, 'p4audit')

    def test_cancel_and_close_are_logged(self):
        from san_xuat.services.planning import cancel_plan, close_plan

        confirm_overall_plan(plan_id=self.overall.pk)
        close_plan(model=SxOverallPlan, plan_id=self.overall.pk)
        actions = set(SxPlanAuditLog.objects.values_list('action', flat=True))
        self.assertIn(SxPlanAuditLog.ACTION_CLOSE, actions)

        other = create_overall_plan(
            name='KH cancel', date_from=date(2026, 9, 1), date_to=date(2026, 9, 5),
        )
        cancel_plan(model=SxOverallPlan, plan_id=other.pk, reason='Đơn hủy')
        cancel_log = SxPlanAuditLog.objects.filter(
            action=SxPlanAuditLog.ACTION_CANCEL, object_code=other.code,
        ).first()
        self.assertIsNotNone(cancel_log)
        self.assertIn('Đơn hủy', cancel_log.summary)

    def test_explode_detail_plan_logged(self):
        confirm_overall_plan(plan_id=self.overall.pk)
        explode_detail_plan_from_overall(overall_plan_id=self.overall.pk, user=self.user)
        log = SxPlanAuditLog.objects.filter(object_type='SxDetailPlan').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, SxPlanAuditLog.ACTION_EXPLODE)

    def test_audit_page_renders(self):
        confirm_overall_plan(plan_id=self.overall.pk, user=self.user)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('san_xuat:plan_audit_log'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.overall.code)

    def test_audit_page_filters(self):
        confirm_overall_plan(plan_id=self.overall.pk, user=self.user)
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('san_xuat:plan_audit_log'),
            {'object_type': 'SxDetailPlan', 'action': 'confirm'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, self.overall.code)


# ---------------------------------------------------------------------------
# 6. Lấy mẫu AQL — ISO 2859-1
# ---------------------------------------------------------------------------

class AqlSamplingTests(TestCase):
    def test_code_letters_level_ii(self):
        from san_xuat.services.aql import code_letter

        self.assertEqual(code_letter(100, 'II'), 'F')
        self.assertEqual(code_letter(500, 'II'), 'H')
        self.assertEqual(code_letter(1000, 'II'), 'J')
        self.assertEqual(code_letter(5000, 'II'), 'L')

    def test_standard_plans_aql_2_5(self):
        from san_xuat.services.aql import aql_sample_plan

        cases = {
            100: (20, 1),
            200: (32, 2),
            400: (50, 3),
            1000: (80, 5),
            2000: (125, 7),
            5000: (200, 10),
        }
        for lot, (sample, accept) in cases.items():
            plan = aql_sample_plan(lot_size=lot, aql=Decimal('2.5'))
            self.assertEqual(plan.sample_size, sample, f'lô {lot}')
            self.assertEqual(plan.accept, accept, f'lô {lot}')
            self.assertEqual(plan.reject, accept + 1)

    def test_standard_plans_aql_1_0_and_4_0(self):
        from san_xuat.services.aql import aql_sample_plan

        self.assertEqual(aql_sample_plan(lot_size=1000, aql=Decimal('1.0')).accept, 2)
        self.assertEqual(aql_sample_plan(lot_size=1000, aql=Decimal('4.0')).accept, 7)

    def test_arrow_down_uses_larger_sample(self):
        from san_xuat.services.aql import aql_sample_plan

        # Lô 30 ở mức II → chữ mã D (n=8), AQL 1.0 cần n=32 → mũi tên xuống,
        # nhưng n vượt cỡ lô nên kiểm 100%.
        plan = aql_sample_plan(lot_size=30, aql=Decimal('1.0'))
        self.assertEqual(plan.arrow, 'down')
        self.assertTrue(plan.full_inspection)
        self.assertEqual(plan.sample_size, 30)
        self.assertEqual(plan.accept, 0)

    def test_arrow_up_caps_at_21(self):
        from san_xuat.services.aql import aql_sample_plan

        plan = aql_sample_plan(lot_size=600000, aql=Decimal('6.5'))
        self.assertEqual(plan.arrow, 'up')
        self.assertEqual(plan.accept, 21)

    def test_special_level_smaller_sample(self):
        from san_xuat.services.aql import aql_sample_plan

        normal = aql_sample_plan(lot_size=5000, aql=Decimal('2.5'), inspection_level='II')
        special = aql_sample_plan(lot_size=5000, aql=Decimal('2.5'), inspection_level='S-2')
        self.assertLess(special.sample_size, normal.sample_size)

    def test_non_standard_aql_normalized(self):
        from san_xuat.services.aql import normalize_aql

        self.assertEqual(normalize_aql(Decimal('2.4')), Decimal('2.5'))
        self.assertEqual(normalize_aql(Decimal('0')), Decimal('2.5'))

    def test_invalid_lot_raises(self):
        from san_xuat.services.aql import AqlError, aql_sample_plan

        with self.assertRaises(AqlError):
            aql_sample_plan(lot_size=0)

    def test_compute_sample_qty_with_aql_method(self):
        from san_xuat.services.qc import compute_sample_qty

        method = SxQcSamplingMethod.objects.create(
            code='AQL-25', name='AQL 2.5 mức II',
            method_type=SxQcSamplingMethod.TYPE_AQL,
            aql_level=Decimal('2.5'), inspection_level='II',
        )
        result = compute_sample_qty(method, Decimal('1000'))
        self.assertEqual(result.required_qty, Decimal('80'))
        self.assertEqual(result.max_defect_allowed, Decimal('5'))

    def test_compute_sample_qty_percent_and_fixed_unchanged(self):
        from san_xuat.services.qc import compute_sample_qty

        pct = SxQcSamplingMethod.objects.create(
            code='PCT-10', name='10%',
            method_type=SxQcSamplingMethod.TYPE_PERCENT, sample_value=Decimal('10'),
        )
        fixed = SxQcSamplingMethod.objects.create(
            code='FIX-5', name='5 cái',
            method_type=SxQcSamplingMethod.TYPE_FIXED, sample_value=Decimal('5'),
        )
        self.assertEqual(compute_sample_qty(pct, Decimal('200')).required_qty, Decimal('20'))
        self.assertEqual(compute_sample_qty(fixed, Decimal('200')).required_qty, Decimal('5'))
        self.assertEqual(compute_sample_qty(fixed, Decimal('200')).max_defect_allowed, Decimal('0'))

    def test_sample_never_exceeds_lot(self):
        from san_xuat.services.qc import compute_sample_qty

        fixed = SxQcSamplingMethod.objects.create(
            code='FIX-500', name='500 cái',
            method_type=SxQcSamplingMethod.TYPE_FIXED, sample_value=Decimal('500'),
        )
        self.assertEqual(compute_sample_qty(fixed, Decimal('30')).required_qty, Decimal('30'))


class CriticalQcTests(TestCase):
    def test_critical_stage_detected_from_routing(self):
        from san_xuat.ie_models import SxRouting, SxRoutingLine
        from san_xuat.services.qc import stage_requires_inspection

        routing = SxRouting.objects.create(style_code='SP-CRIT', is_active=True)
        SxRoutingLine.objects.create(
            routing=routing, seq_no=10, op_name_vi='Kiểm cuối', critical_qc=True,
        )
        SxRoutingLine.objects.create(
            routing=routing, seq_no=20, op_name_vi='Đóng gói', critical_qc=False,
        )
        self.assertTrue(
            stage_requires_inspection(product_code='SP-CRIT', stage_name='Kiểm cuối')
        )
        self.assertFalse(
            stage_requires_inspection(product_code='SP-CRIT', stage_name='Đóng gói')
        )

    def test_missing_data_is_safe(self):
        from san_xuat.services.qc import stage_requires_inspection

        self.assertFalse(stage_requires_inspection(product_code='', stage_name=''))
        self.assertFalse(stage_requires_inspection(product_code='KHONG-CO', stage_name='May'))


class PurchaseOrderPageTests(TestCase):
    """Trang DMH phải render được với context P4 mới."""

    def setUp(self):
        self.user = _director('p4po')
        self.client.force_login(self.user)
        _material('VAI-PAGE')
        WarehouseLocation.objects.create(
            code='KHO-PAGE', name='Kho', location_kind=WarehouseLocation.KIND_STOCK,
        )
        self.po = SxPurchaseOrder.objects.create(
            code='DMH-PAGE-1', status=SxPurchaseOrder.STATUS_CONFIRMED,
            expected_date=date(2026, 9, 3),
        )
        self.po.lines.create(
            material_code='VAI-PAGE', qty_ordered=Decimal('10'), unit_price=Decimal('5000'),
        )

    def test_detail_renders(self):
        resp = self.client.get(reverse('san_xuat:purchase_order_detail', args=[self.po.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nhập kho nguyên phụ liệu')

    def test_create_receipt_action(self):
        resp = self.client.post(
            reverse('san_xuat:purchase_order_detail', args=[self.po.pk]),
            {'action': 'create_receipt'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(StockReceipt.objects.filter(po_number='DMH-PAGE-1').exists())

    def test_downtime_page_renders_oee(self):
        _center('T-PAGE', 'Tổ trang', heads=2)
        resp = self.client.get(reverse('san_xuat:downtime_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Sẵn sàng')

    def test_npl_plan_detail_renders_need_date(self):
        mat = _material('VAI-NPLPAGE')
        _product_with_bom('SP-NPLPAGE', [(mat, '1')])
        overall = create_overall_plan(
            name='KH npl page', date_from=date(2026, 9, 1), date_to=date(2026, 9, 3),
        )
        add_overall_plan_line(
            plan_id=overall.pk, product_code='SP-NPLPAGE', qty_planned=Decimal('10'),
        )
        confirm_overall_plan(plan_id=overall.pk)
        plan = explode_material_plan(overall_plan_id=overall.pk)
        resp = self.client.get(reverse('san_xuat:plan_npl_detail', args=[plan.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ngày cần')


class DetailPlanRescheduleAuditTests(TestCase):
    def test_reschedule_logged(self):
        from san_xuat.services.scheduling import schedule_detail_plan_by_capacity

        user = _director('p4resched')
        sew = _center('T-RS', 'May RS', heads=2)
        _product_with_bom('SP-RS', [], steps=[('May', sew, '5')])
        overall = create_overall_plan(
            name='KH resched', date_from=date(2026, 9, 1), date_to=date(2026, 9, 4),
        )
        add_overall_plan_line(
            plan_id=overall.pk, product_code='SP-RS', qty_planned=Decimal('100'),
        )
        confirm_overall_plan(plan_id=overall.pk)
        res = schedule_detail_plan_by_capacity(overall_plan_id=overall.pk, user=user)
        self.assertGreater(res.lines_created, 0)
        log = SxPlanAuditLog.objects.filter(
            action=SxPlanAuditLog.ACTION_RESCHEDULE,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.username, 'p4resched')
        self.assertTrue(SxDetailPlan.objects.filter(pk=res.detail_plan.pk).exists())


class NplPurchaseRequestNeedDateTests(TestCase):
    def test_pr_without_need_date_keeps_explicit_due_date(self):
        from san_xuat.hub_models import SxMaterialPlan

        plan = SxMaterialPlan.objects.create(
            code='KHNVL-P4-ND', name='No need date',
            status=SxOverallPlan.STATUS_CONFIRMED,
        )
        plan.lines.create(
            material_code='VAI-ND', qty_required=Decimal('10'), qty_shortfall=Decimal('10'),
        )
        pr = build_pr_from_material_plan(
            material_plan_id=plan.pk, due_date=date(2026, 10, 1),
        )
        self.assertEqual(pr.due_date, date(2026, 10, 1))
        self.assertEqual(pr.status, SxNplPurchaseRequest.STATUS_DRAFT)

    def test_confirm_po_logged(self):
        po = SxPurchaseOrder.objects.create(
            code='DMH-P4-LOG', status=SxPurchaseOrder.STATUS_DRAFT,
        )
        po.lines.create(material_code='VAI-LOG', qty_ordered=Decimal('5'))
        confirm_purchase_order(order_id=po.pk)
        self.assertTrue(
            SxPlanAuditLog.objects.filter(
                object_code='DMH-P4-LOG', action=SxPlanAuditLog.ACTION_CONFIRM,
            ).exists()
        )


class GeneralSettingsFormTests(TestCase):
    """Các knob lập kế hoạch phải nằm trên form thiết lập (P1 thiếu, P4 bù)."""

    def setUp(self):
        self.user = _director('p4settings')
        self.client.force_login(self.user)

    def test_planning_fields_rendered(self):
        resp = self.client.get(reverse('san_xuat:general_settings'))
        self.assertEqual(resp.status_code, 200)
        for name in ('plan_capacity_mode', 'plan_workdays', 'npl_prep_days', 'mo_late_alert_days'):
            self.assertContains(resp, f'name="{name}"')

    def test_saving_settings_persists_planning_knobs(self):
        from san_xuat.hub_models import SxGeneralSettings

        cfg = SxGeneralSettings.load()
        payload = {}
        for name, field in SxGeneralSettingsForm_fields():
            value = getattr(cfg, name)
            if isinstance(value, bool):
                if value:
                    payload[name] = 'on'
            elif value is not None:
                payload[name] = str(value)
        payload['npl_prep_days'] = '4'
        payload['mo_late_alert_days'] = '5'

        resp = self.client.post(reverse('san_xuat:general_settings'), payload, follow=True)
        self.assertEqual(resp.status_code, 200)
        cfg.refresh_from_db()
        self.assertEqual(cfg.npl_prep_days, 4)
        self.assertEqual(cfg.mo_late_alert_days, 5)


def SxGeneralSettingsForm_fields():
    from san_xuat.forms_settings import SxGeneralSettingsForm

    form = SxGeneralSettingsForm()
    return [(name, field) for name, field in form.fields.items()]
