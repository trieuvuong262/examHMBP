"""Sửa Nhu cầu BOM trên đơn → YCX còn mở + phiếu xuất NPL nháp đi theo nhu cầu mới."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED, ISSUE_TYPE_PRODUCTION
from kho_npl.models import Material, MaterialCategory, StockIssue, Unit, WarehouseLocation
from san_xuat.hub_models import SxMaterialIssueRequest, SxProductionOrder
from san_xuat.services.dispatch import sync_open_ycx_with_order_need
from san_xuat.services.order_routing import update_order_line_bom_overrides
from san_xuat.services.sales_orders import LineInput, create_sales_order


def _bom_row(code, qty_per_unit):
    return {'material_code': code, 'material_name': code, 'unit': 'm',
            'qty': qty_per_unit, 'qty_std': qty_per_unit, 'qty_mode': 'qty', 'scrap_pct': 0}


class YcxNeedSyncTests(TestCase):
    def setUp(self):
        cat = MaterialCategory.objects.create(code='ys-cat', name='YS')
        unit = Unit.objects.create(code='ys-m', name='Met')
        self.loc = WarehouseLocation.objects.create(code='YS-LOC', name='Kho YS', is_active=True)
        self.mat_a = Material.objects.create(code='YS-A', name='Vai A', category=cat, unit=unit)
        self.mat_b = Material.objects.create(code='YS-B', name='Chi B', category=cat, unit=unit)
        self.order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='YS-SP', qty=Decimal('10'), product_name='Ao')],
        )
        self.line = self.order.lines.get()
        # ĐM 10 m/SP × 10 SP = nhu cầu 100 m; chỉ B = 2 × 10 = 20.
        self.line.bom_line_overrides = [_bom_row('YS-A', 10), _bom_row('YS-B', 2)]
        self.line.save(update_fields=['bom_line_overrides'])
        self.mo = SxProductionOrder.objects.create(
            code='LSX-YS-1', product_code='YS-SP', qty=Decimal('10'),
            order_date=timezone.localdate(), sales_order=self.order,
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        self._n = 0

    def _issue(self, status, lines):
        self._n += 1
        issue = StockIssue.objects.create(
            number=f'PX-YS-{self._n}', issue_date=timezone.localdate(),
            issue_type=ISSUE_TYPE_PRODUCTION, production_order=self.mo.code,
            sales_order=self.order, status=status,
        )
        for mat, qty in lines:
            issue.lines.create(material=mat, quantity=qty, qty_base=qty, location=self.loc)
        return issue

    def _ycx(self, status, lines, issue=None):
        """lines = [(material, qty_requested, qty_issued)]."""
        self._n += 1
        req = SxMaterialIssueRequest.objects.create(
            code=f'YCX-YS-{self._n}', production_order=self.mo, status=status,
            request_date=timezone.localdate(), stock_issue=issue,
        )
        for mat, qty_req, qty_iss in lines:
            req.lines.create(material_code=mat.code, material_name=mat.name, bom_material_code=mat.code,
                             qty_requested=qty_req, qty_issued=qty_iss)
        if issue is not None:
            req.stock_issues.add(issue)
        return req

    def _set_need(self, qty_a, qty_b=2):
        rows = [_bom_row('YS-A', qty_a)] if qty_a else []
        self.line.bom_line_overrides = rows + [_bom_row('YS-B', qty_b)]
        self.line.save(update_fields=['bom_line_overrides'])

    @staticmethod
    def _issue_qty(issue, mat):
        return sum((ln.qty_base for ln in issue.lines.filter(material=mat)), Decimal('0'))

    def test_decrease_updates_ycx_and_draft_issue(self):
        issue = self._issue(DOC_STATUS_DRAFT, [(self.mat_a, Decimal('100')), (self.mat_b, Decimal('20'))])
        req = self._ycx('submitted', [(self.mat_a, Decimal('100'), 0), (self.mat_b, Decimal('20'), 0)], issue)
        self._set_need(8)  # 80 m
        res = sync_open_ycx_with_order_need(self.order)
        self.assertEqual(res.lines_changed, 1)
        self.assertEqual(req.lines.get(material_code='YS-A').qty_requested, Decimal('80'))
        self.assertEqual(self._issue_qty(issue, self.mat_a), Decimal('80'))
        self.assertEqual(self._issue_qty(issue, self.mat_b), Decimal('20'))  # B không đổi

    def test_increase_updates_ycx_and_draft_issue(self):
        issue = self._issue(DOC_STATUS_DRAFT, [(self.mat_a, Decimal('100'))])
        req = self._ycx('submitted', [(self.mat_a, Decimal('100'), 0)], issue)
        self._set_need(12)  # 120 m
        sync_open_ycx_with_order_need(self.order)
        self.assertEqual(req.lines.get().qty_requested, Decimal('120'))
        self.assertEqual(self._issue_qty(issue, self.mat_a), Decimal('120'))

    def test_material_removed_cancels_empty_draft(self):
        issue = self._issue(DOC_STATUS_DRAFT, [(self.mat_a, Decimal('100'))])
        req = self._ycx('submitted', [(self.mat_a, Decimal('100'), 0)], issue)
        self._set_need(0)  # bỏ NPL A khỏi BOM
        res = sync_open_ycx_with_order_need(self.order)
        issue.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual(issue.status, DOC_STATUS_CANCELLED)
        self.assertEqual(req.status, 'cancelled')
        self.assertIn(req.code, res.requests_cancelled)

    def test_posted_issue_untouched_and_over_issue_reported(self):
        posted = self._issue(DOC_STATUS_POSTED, [(self.mat_a, Decimal('60'))])
        req = self._ycx('partial', [(self.mat_a, Decimal('100'), Decimal('60'))], posted)
        self._set_need(5)  # 50 m < 60 m đã xuất
        res = sync_open_ycx_with_order_need(self.order)
        req.refresh_from_db()
        self.assertEqual(req.lines.get().qty_requested, Decimal('60'))  # không xuất thêm
        self.assertEqual(req.status, 'done')
        self.assertEqual(self._issue_qty(posted, self.mat_a), Decimal('60'))  # phiếu đã ghi sổ giữ nguyên
        self.assertEqual(res.over_issued, [('YS-A', Decimal('60'), Decimal('50.000'))])

    def test_partial_remaining_follows_new_need(self):
        posted = self._issue(DOC_STATUS_POSTED, [(self.mat_a, Decimal('60'))])
        req = self._ycx('partial', [(self.mat_a, Decimal('100'), Decimal('60'))], posted)
        self._set_need(9)  # 90 m → còn phải xuất 30
        sync_open_ycx_with_order_need(self.order)
        req.refresh_from_db()
        self.assertEqual(req.lines.get().qty_requested, Decimal('90'))
        self.assertEqual(req.status, 'partial')

    def test_save_bom_on_order_runs_sync(self):
        issue = self._issue(DOC_STATUS_DRAFT, [(self.mat_a, Decimal('100'))])
        req = self._ycx('submitted', [(self.mat_a, Decimal('100'), 0)], issue)
        res = update_order_line_bom_overrides(
            self.line, rows=[_bom_row('YS-A', 7.5), _bom_row('YS-B', 2)],
        )
        self.assertTrue(res.changed)
        self.assertEqual(req.lines.get().qty_requested, Decimal('75'))
        self.assertEqual(self._issue_qty(issue, self.mat_a), Decimal('75'))

    def test_no_issue_no_change(self):
        res = sync_open_ycx_with_order_need(self.order)
        self.assertFalse(res.changed)
        self.assertEqual(res.over_issued, [])
