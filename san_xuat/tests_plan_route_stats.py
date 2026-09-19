"""Thong ke lo trinh - tong SL theo bo phan x ngay."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase

from san_xuat.services.plan_board import build_route_stats


def _day(d, *, today=False, off=False):
    return SimpleNamespace(date=d, is_today=today, is_off=off, is_weekend=False)


def _cell(d, qty=None, *, done=None, off=False):
    bar = None
    if (qty is not None or done is not None) and not off:
        bar = SimpleNamespace(
            qty_label=str(qty) if qty is not None else '0',
            done_qty_label=str(done) if done is not None else '0',
        )
    return SimpleNamespace(date=d, bar=bar, is_off=off)


def _stage(slug, cells, label='', work_center_id=0):
    return SimpleNamespace(
        slug=slug,
        short_label=label,
        label=label,
        work_center_id=work_center_id,
        cells=cells,
    )


def _row(code, stages, **extra):
    order = SimpleNamespace(pk=extra.get('pk', 1), code=code)
    return SimpleNamespace(order=order, stage_rows=stages)


class BuildRouteStatsTests(TestCase):
    def test_empty_board(self):
        self.assertEqual(build_route_stats(None).stages, [])
        self.assertEqual(build_route_stats(SimpleNamespace(rows=[], days=[])).stages, [])

    def test_sums_by_department_and_day(self):
        d1 = date(2026, 10, 1)
        d2 = date(2026, 10, 2)
        d3 = date(2026, 10, 3)
        days = [_day(d1), _day(d2), _day(d3)]
        board = SimpleNamespace(
            days=days,
            rows=[
                _row('DH-1', [
                    _stage('cat', [_cell(d1, 800), _cell(d2, None), _cell(d3, 2000)], 'CAT', 22),
                    _stage('may', [_cell(d1, None), _cell(d2, 500), _cell(d3, None)], 'MAY', 25),
                ], pk=1),
                _row('DH-2', [
                    _stage('cat', [_cell(d1, None), _cell(d2, None), _cell(d3, 800)], 'CAT', 22),
                    _stage('may', [_cell(d1, None), _cell(d2, 300), _cell(d3, None)], 'MAY', 25),
                ], pk=2),
            ],
        )
        stats = build_route_stats(board)
        self.assertEqual([s.label for s in stats.stages], ['CAT', 'MAY'])

        cat = stats.stages[0]
        self.assertEqual([c.qty for c in cat.cells], [
            Decimal('800.00'), Decimal('0.00'), Decimal('2800.00'),
        ])
        self.assertEqual(cat.total, Decimal('3600.00'))

        may = stats.stages[1]
        self.assertEqual([c.qty for c in may.cells], [
            Decimal('0.00'), Decimal('800.00'), Decimal('0.00'),
        ])
        self.assertEqual(may.total, Decimal('800.00'))

    def test_sums_done_by_department_and_day(self):
        d1 = date(2026, 10, 1)
        d2 = date(2026, 10, 2)
        days = [_day(d1), _day(d2)]
        board = SimpleNamespace(
            days=days,
            rows=[
                _row('DH-1', [
                    _stage('cat', [_cell(d1, 800, done=100), _cell(d2, 200, done=50)], 'CAT', 22),
                    _stage('may', [_cell(d1, 500, done=0), _cell(d2, 300, done=120)], 'MAY', 25),
                ], pk=1),
                _row('DH-2', [
                    _stage('cat', [_cell(d1, 100, done=80), _cell(d2, None, done=None)], 'CAT', 22),
                ], pk=2),
            ],
        )
        stats = build_route_stats(board)
        cat = stats.stages[0]
        self.assertEqual([c.done_qty for c in cat.cells], [
            Decimal('180.00'), Decimal('50.00'),
        ])
        self.assertEqual(cat.done_total, Decimal('230.00'))
        may = stats.stages[1]
        self.assertEqual([c.done_qty for c in may.cells], [
            Decimal('0.00'), Decimal('120.00'),
        ])
        self.assertEqual(may.done_total, Decimal('120.00'))

    def test_splits_same_slug_different_work_centers(self):
        d1 = date(2026, 10, 1)
        days = [_day(d1)]
        board = SimpleNamespace(
            days=days,
            rows=[
                _row('DH-1', [
                    _stage('may', [_cell(d1, 60)], 'MAY A', 25),
                    _stage('may', [_cell(d1, 40)], 'MAY B', 26),
                ]),
            ],
        )
        stats = build_route_stats(board)
        self.assertEqual(len(stats.stages), 2)
        self.assertEqual([s.label for s in stats.stages], ['MAY A', 'MAY B'])
        self.assertEqual(stats.stages[0].total, Decimal('60.00'))
        self.assertEqual(stats.stages[1].total, Decimal('40.00'))

    def test_skips_npl_and_off_days(self):
        d1 = date(2026, 10, 1)
        d2 = date(2026, 10, 2)
        days = [_day(d1), _day(d2, off=True)]
        board = SimpleNamespace(
            days=days,
            rows=[
                _row('DH-1', [
                    _stage('npl', [_cell(d1, 99), _cell(d2, 99, off=True)], 'NPL'),
                    _stage('cat', [_cell(d1, 10), _cell(d2, 50, off=True)], 'CAT', 1),
                ]),
            ],
        )
        stats = build_route_stats(board)
        self.assertEqual([s.slug for s in stats.stages], ['cat'])
        self.assertEqual(stats.stages[0].cells[0].qty, Decimal('10.00'))
        self.assertEqual(stats.stages[0].cells[1].qty, Decimal('0.00'))
        self.assertTrue(stats.stages[0].cells[1].is_off)
