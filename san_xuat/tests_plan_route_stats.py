"""Thống kê bảng lộ trình — tổng đã làm / chưa làm theo công đoạn và đơn."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from san_xuat.services.plan_board import build_route_stats


def _stage(slug, planned, done, label='', work_center_id=0):
    return SimpleNamespace(
        slug=slug,
        short_label=label,
        label=label,
        work_center_id=work_center_id,
        team_qty_total=str(planned),
        total_label=str(planned),
        done_total_label=str(done),
        planned_qty=Decimal(str(planned)),
    )


def _row(code, qty, stages, **extra):
    order = SimpleNamespace(pk=extra.get('pk', 1), code=code)
    return SimpleNamespace(
        order=order,
        qty_label=str(qty),
        product_code_label=extra.get('product_code_label', 'SP-1'),
        product_name_label=extra.get('product_name_label', 'Áo'),
        subtitle=extra.get('subtitle', ''),
        status_key=extra.get('status_key', 'in_progress'),
        status_label=extra.get('status_label', 'Đang sản xuất'),
        is_late=extra.get('is_late', False),
        stage_rows=stages,
    )


class BuildRouteStatsTests(TestCase):
    def test_empty_board(self):
        self.assertEqual(build_route_stats(None).order_count, 0)
        self.assertEqual(build_route_stats(SimpleNamespace(rows=[])).order_count, 0)

    def test_aggregates_by_stage_and_order(self):
        board = SimpleNamespace(rows=[
            _row('DH-1', 100, [
                _stage('cat', 100, 80, 'Cắt'),
                _stage('may', 100, 20, 'May'),
            ], pk=1),
            _row('DH-2', 50, [
                _stage('cat', 50, 50, 'Cắt'),
                _stage('may', 50, 10, 'May'),
            ], pk=2),
        ])
        stats = build_route_stats(board)

        self.assertEqual(stats.order_count, 2)
        self.assertEqual(stats.planned, Decimal('150.00'))
        self.assertEqual([s.slug for s in stats.stages], ['cat', 'may'])

        cat = stats.stages[0]
        self.assertEqual(cat.planned, Decimal('150.00'))
        self.assertEqual(cat.done, Decimal('130.00'))
        self.assertEqual(cat.remaining, Decimal('20.00'))
        self.assertEqual(cat.order_count, 2)

        may = stats.stages[1]
        self.assertEqual(may.planned, Decimal('150.00'))
        self.assertEqual(may.done, Decimal('30.00'))
        self.assertEqual(may.remaining, Decimal('120.00'))

        first = stats.orders[0]
        self.assertEqual(first.order.code, 'DH-1')
        self.assertEqual(first.qty, Decimal('100.00'))
        self.assertEqual(first.cells[0].done, Decimal('80.00'))
        self.assertEqual(first.cells[1].remaining, Decimal('80.00'))
        self.assertEqual(first.done, Decimal('20.00'))
        self.assertEqual(first.remaining, Decimal('80.00'))

        self.assertEqual(stats.done, Decimal('30.00'))
        self.assertEqual(stats.remaining, Decimal('120.00'))

    def test_splits_same_stage_across_work_centers(self):
        board = SimpleNamespace(rows=[
            _row('DH-1', 100, [
                _stage('may', 60, 40),
                _stage('may', 40, 10),
            ]),
        ])
        stats = build_route_stats(board)
        self.assertEqual(len(stats.stages), 1)
        self.assertEqual(stats.stages[0].planned, Decimal('100.00'))
        self.assertEqual(stats.stages[0].done, Decimal('50.00'))
        self.assertEqual(stats.orders[0].cells[0].planned, Decimal('100.00'))

    def test_skips_npl_and_missing_stage(self):
        board = SimpleNamespace(rows=[
            _row('DH-1', 10, [
                _stage('npl', 10, 10),
                _stage('cat', 10, 4),
            ]),
        ])
        stats = build_route_stats(board)
        self.assertEqual([s.slug for s in stats.stages], ['cat'])
        self.assertTrue(stats.orders[0].cells[0].present)
    def test_uses_ob_department_label_not_sheet_name(self):
        board = SimpleNamespace(rows=[
            _row('DH-1', 100, [
                _stage('cat', 100, 40, 'CẮT, TRẢI VẢI', work_center_id=22),
                _stage('inep', 100, 10, 'Ép / in thử', work_center_id=31),
            ]),
        ])
        stats = build_route_stats(board)
        self.assertEqual([s.label for s in stats.stages], ['CẮT, TRẢI VẢI', 'Ép / in thử'])
        self.assertNotIn('In/ép', [s.label for s in stats.stages])

    def test_splits_same_slug_different_ob_teams(self):
        board = SimpleNamespace(rows=[
            _row('DH-1', 100, [
                _stage('may', 60, 20, 'MAY (152A)', work_center_id=25),
                _stage('may', 40, 10, 'MAY (Vĩnh Lộc)', work_center_id=26),
            ]),
        ])
        stats = build_route_stats(board)
        self.assertEqual(len(stats.stages), 2)
        self.assertEqual([s.label for s in stats.stages], ['MAY (152A)', 'MAY (Vĩnh Lộc)'])
        self.assertEqual(stats.stages[0].planned, Decimal('60.00'))
        self.assertEqual(stats.stages[1].planned, Decimal('40.00'))

