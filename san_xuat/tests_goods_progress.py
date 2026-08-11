from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxSalesOrder,
)
from san_xuat.services.goods_progress import build_goods_progress_board


class GoodsProgressBoardTests(TestCase):
    def _so(self, code, priority='normal', due=None):
        return SxSalesOrder.objects.create(
            code=code,
            customer_name='KH test',
            request_date=timezone.localdate(),
            due_date=due,
            plan_priority=priority,
            is_demo=False,
        )

    def _mo(self, code, qty=20, so=None, due=None, status=None):
        return SxProductionOrder.objects.create(
            code=code,
            product_code='SP-TEST',
            product_name='Ao test',
            qty=Decimal(str(qty)),
            order_date=timezone.localdate(),
            due_date=due,
            status=status or SxProductionOrder.STATUS_IN_PROGRESS,
            sales_order=so,
            is_demo=False,
        )

    def _stat(self, mo, process_name, qty, size='M'):
        n = SxProductionStat.objects.count() + 1
        return SxProductionStat.objects.create(
            code=f'TKSX-GP-{n:04d}',
            production_order=mo,
            stat_date=timezone.localdate(),
            process_name=process_name,
            qty_good=Decimal(str(qty)),
            status=SxProductionStat.STATUS_CONFIRMED,
            size_label=size,
            is_demo=False,
        )

    def test_sorts_overdue_and_urgent_first(self):
        today = timezone.localdate()
        so_hot = self._so('DH-GP-HOT', priority=SxSalesOrder.PRIORITY_CRITICAL)
        mo_hot = self._mo('LSX-GP-HOT', so=so_hot, due=today + timedelta(days=5))
        mo_late = self._mo('LSX-GP-LATE', due=today - timedelta(days=2))
        mo_ok = self._mo('LSX-GP-OK', due=today + timedelta(days=20))
        for mo in (mo_hot, mo_late, mo_ok):
            SxProductionOrderLine.objects.create(
                production_order=mo, size_label='M', color_code='NVY', qty=Decimal('20'),
            )

        board = build_goods_progress_board(today=today)
        codes = [r.mo.code for r in board.rows]
        self.assertEqual(codes[:3], ['LSX-GP-LATE', 'LSX-GP-HOT', 'LSX-GP-OK'])
        by_code = {r.mo.code: r for r in board.rows}
        self.assertTrue(by_code['LSX-GP-LATE'].is_overdue)
        self.assertTrue(by_code['LSX-GP-HOT'].is_hot)
        self.assertEqual(by_code['LSX-GP-HOT'].priority_label, 'Rất gấp')
        self.assertGreaterEqual(board.hot_count, 2)
        self.assertEqual(board.overdue_count, 1)

    def test_shows_other_teams_and_current_location(self):
        mo = self._mo('LSX-GP-FLOW', qty=20)
        SxProductionOrderLine.objects.create(
            production_order=mo, size_label='M', color_code='NVY', qty=Decimal('20'),
        )
        self._stat(mo, 'Áo TT + TS + Tay', 12)

        board = build_goods_progress_board()
        row = next(r for r in board.rows if r.mo.code == 'LSX-GP-FLOW')
        labels = [c.label for c in row.cells]
        self.assertGreaterEqual(len(labels), 6)
        by_slug = {c.slug: c for c in row.cells}
        self.assertEqual(by_slug['cat'].done, Decimal('12'))
        self.assertEqual(by_slug['inep'].waiting, Decimal('12'))
        self.assertEqual(row.current_slug, 'cat')

        self._stat(mo, 'Áo TT + TS + Tay', 8)
        board2 = build_goods_progress_board()
        row2 = next(r for r in board2.rows if r.mo.code == 'LSX-GP-FLOW')
        self.assertEqual(row2.current_slug, 'inep')

    def test_url_resolves(self):
        self.assertEqual(reverse('san_xuat:team_work_goods'), '/san-xuat/cong-viec-to/tien-do-hang-hoa/')
