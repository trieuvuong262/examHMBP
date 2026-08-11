from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxProductionOrderLine, SxProductionStat
from san_xuat.services.handover_status import build_handover_board, build_mo_handover_row


class HandoverStatusFromTeamProgressTests(TestCase):
    def _mo(self, code, qty=20):
        return SxProductionOrder.objects.create(
            code=code,
            product_code='SP-TEST',
            product_name='Ao test',
            qty=Decimal(str(qty)),
            order_date=timezone.localdate(),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
            is_demo=False,
        )

    def _stat(self, mo, process_name, qty, size='M', code=None):
        n = SxProductionStat.objects.count() + 1
        return SxProductionStat.objects.create(
            code=code or f'TKSX-HO-{n:04d}',
            production_order=mo,
            stat_date=timezone.localdate(),
            process_name=process_name,
            qty_good=Decimal(str(qty)),
            status=SxProductionStat.STATUS_CONFIRMED,
            size_label=size,
            is_demo=False,
        )

    def test_waiting_at_next_team_from_cut_qty(self):
        mo = self._mo('LSX-HO-001', qty=20)
        SxProductionOrderLine.objects.create(
            production_order=mo, size_label='M', color_code='NVY', qty=Decimal('20'),
        )
        self._stat(mo, 'Áo TT + TS + Tay', 12)

        row = build_mo_handover_row(mo)
        by_key = {c.group_key: c for c in row.cells}
        self.assertEqual(by_key['CAT'].done, Decimal('12'))
        self.assertEqual(by_key['IN_EP'].waiting, Decimal('12'))
        self.assertEqual(by_key['IN_EP'].done, Decimal('0'))
        self.assertEqual(by_key['THEU'].waiting, Decimal('0'))
        self.assertEqual(row.waiting_total, Decimal('12'))
        self.assertEqual(row.bottleneck, 'In - Ép')

    def test_board_search_and_team_filter(self):
        mo = self._mo('LSX-HO-002', qty=10)
        SxProductionOrderLine.objects.create(
            production_order=mo, size_label='L', color_code='BLK', qty=Decimal('10'),
        )
        self._stat(mo, 'Áo TT + TS + Tay', 10, size='L')
        self._stat(mo, 'Lá cổ', 4, size='L')

        board = build_handover_board(search='HO-002')
        self.assertEqual(board.mo_count, 1)
        inep = next(q for q in board.queues if q.slug == 'inep')
        self.assertEqual(inep.waiting, Decimal('6'))

        may_board = build_handover_board(search='HO-002', team_slug='may')
        self.assertEqual(may_board.mo_count, 0)


from san_xuat.services.team_work import close_team_job, is_team_job_closed, reopen_team_job


class TeamWorkCloseTests(TestCase):
    def test_close_is_formal_not_a_gate(self):
        mo = SxProductionOrder.objects.create(
            code='LSX-HO-CLOSE',
            product_code='SP-TEST',
            qty=Decimal('10'),
            order_date=timezone.localdate(),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
            is_demo=False,
        )
        SxProductionOrderLine.objects.create(
            production_order=mo, size_label='M', color_code='NVY', qty=Decimal('10'),
        )
        n = SxProductionStat.objects.count() + 1
        SxProductionStat.objects.create(
            code=f'TKSX-HO-{n:04d}',
            production_order=mo,
            stat_date=timezone.localdate(),
            process_name='Áo TT + TS + Tay',
            qty_good=Decimal('8'),
            status=SxProductionStat.STATUS_CONFIRMED,
            size_label='M',
            is_demo=False,
        )
        close_team_job(mo_id=mo.pk, team_slug='cat')
        self.assertTrue(is_team_job_closed(mo_id=mo.pk, team_slug='cat'))
        self.assertFalse(is_team_job_closed(mo_id=mo.pk, team_slug='may'))
        row = build_mo_handover_row(mo)
        by_key = {c.group_key: c for c in row.cells}
        self.assertEqual(by_key['CAT'].done, Decimal('8'))
        self.assertEqual(by_key['IN_EP'].waiting, Decimal('8'))
        reopen_team_job(mo_id=mo.pk, team_slug='cat')
        self.assertFalse(is_team_job_closed(mo_id=mo.pk, team_slug='cat'))
