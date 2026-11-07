"""LSX nháp cho đơn đã xác nhận còn Chờ xếp trên KHSX."""

from datetime import date
from decimal import Decimal

from django.test import TestCase, TransactionTestCase

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder, SxSalesOrderLine, SxWorkCenter
from san_xuat.models import BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.dispatch import DispatchError, mo_release
from san_xuat.services.order_draft_mo import sync_order_draft_mos
from san_xuat.services.plan_board import (
    derive_plan_status,
    hold_plan_order,
    release_order_to_production,
    unrelease_order_from_production,
)
from san_xuat.services.tech_doc_copy import is_bom_locked


def _product_with_bom(code: str, wc: SxWorkCenter) -> BomVersion:
    doc = ProductTechDoc.objects.create(product_code=code, product_name=f'SP {code}', is_active=True)
    bom = BomVersion.objects.create(tech_doc=doc, version_label='v1', status=BomVersion.STATUS_ACTIVE)
    for i, name in enumerate(('Cắt', 'May'), start=1):
        ProcessStep.objects.create(
            bom=bom,
            sequence=i * 10,
            process_name=name,
            work_center=wc,
            norm_per_hour=Decimal('60'),
            std_time_minutes=Decimal('1'),
        )
    return bom


class _OrderFixture:
    def setUp(self):
        self.wc = SxWorkCenter.objects.create(
            code='WC-DRAFT',
            name='Tổ nháp',
            team_label='Tổ nháp',
            headcount=10,
            shift_minutes_per_head=480,
            efficiency_pct=Decimal('100'),
            capacity_per_day=Decimal('0'),
        )
        self.bom = _product_with_bom('SP-DRAFT-1', self.wc)
        self.order = SxSalesOrder.objects.create(
            code='SXJP:TEST-DRAFT',
            request_date=date(2026, 11, 2),
            due_date=date(2026, 11, 16),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status=SxSalesOrder.PLAN_QUEUED,
        )
        self.line = SxSalesOrderLine.objects.create(
            order=self.order,
            product_code='SP-DRAFT-1',
            product_name='SP nháp',
            qty=Decimal('600'),
            bom_version=self.bom,
        )

    def _drafts(self):
        return list(
            SxProductionOrder.objects.filter(
                sales_order=self.order, status=SxProductionOrder.STATUS_DRAFT,
            )
        )


class OrderDraftMoTests(_OrderFixture, TestCase):
    def test_queued_order_gets_draft_mo(self):
        result = sync_order_draft_mos(self.order.pk)

        self.assertEqual(result.created, 1)
        drafts = self._drafts()
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].qty, Decimal('600'))
        self.assertEqual(drafts[0].bom_version_id, self.bom.pk)
        self.assertTrue(drafts[0].mo_process_steps.exists())
        self.order.refresh_from_db()
        self.assertEqual(derive_plan_status(self.order), SxSalesOrder.PLAN_QUEUED)

    def test_sync_is_idempotent(self):
        sync_order_draft_mos(self.order.pk)
        again = sync_order_draft_mos(self.order.pk)

        self.assertEqual(again.changed, 0)
        self.assertEqual(len(self._drafts()), 1)


    def test_unconfirmed_order_has_no_draft(self):
        self.order.confirm_status = SxSalesOrder.CONFIRM_DRAFT
        self.order.save(update_fields=['confirm_status'])

        sync_order_draft_mos(self.order.pk)

        self.assertEqual(self._drafts(), [])

    def test_draft_does_not_block_hold_or_lock_bom(self):
        sync_order_draft_mos(self.order.pk)

        self.assertFalse(is_bom_locked(self.bom))
        hold_plan_order(order_id=self.order.pk, reason='chờ vải')
        self.order.refresh_from_db()
        self.assertEqual(self.order.plan_status, SxSalesOrder.PLAN_ON_HOLD)
        self.assertEqual(len(self._drafts()), 1)

    def test_manual_release_blocked_while_queued(self):
        sync_order_draft_mos(self.order.pk)

        with self.assertRaises(DispatchError):
            mo_release(mo_id=self._drafts()[0].pk, user=None)

    def test_release_reuses_draft_and_unrelease_reverts_it(self):
        sync_order_draft_mos(self.order.pk)
        draft = self._drafts()[0]

        released = release_order_to_production(order_id=self.order.pk)

        self.assertEqual([mo.pk for mo in released], [draft.pk])
        draft.refresh_from_db()
        self.assertEqual(draft.status, SxProductionOrder.STATUS_RELEASED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.plan_status, SxSalesOrder.PLAN_RELEASED)

        _order, reverted = unrelease_order_from_production(order_id=self.order.pk)

        self.assertEqual(reverted, 1)
        draft.refresh_from_db()
        self.assertEqual(draft.status, SxProductionOrder.STATUS_DRAFT)
        self.order.refresh_from_db()
        self.assertEqual(self.order.plan_status, SxSalesOrder.PLAN_QUEUED)

class OrderDraftMoSignalTests(_OrderFixture, TransactionTestCase):
    """Commit thật: đồng bộ chạy sau khi lưu dòng đơn."""

    def test_order_lines_create_draft_on_commit(self):
        self.assertEqual(len(self._drafts()), 1)

    def test_line_edit_updates_draft(self):
        self.line.qty = Decimal('750')
        self.line.save()

        self.assertEqual(self._drafts()[0].qty, Decimal('750'))

    def test_line_without_bom_cancels_draft(self):
        code = self._drafts()[0].code
        self.line.bom_version = None
        self.line.save()

        self.assertEqual(self._drafts(), [])
        self.assertEqual(
            SxProductionOrder.objects.get(code=code).status, SxProductionOrder.STATUS_CANCELLED,
        )

    def test_reject_order_cancels_draft(self):
        from san_xuat.services.sales_orders import reject_sales_order

        reject_sales_order(order_id=self.order.pk, reason='sai mã')

        self.assertEqual(self._drafts(), [])
