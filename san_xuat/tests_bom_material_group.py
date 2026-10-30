"""BOM dong Nhom gom NPL - bung thanh NPL thanh vien cho don / KHSX / LSX."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from kho_npl.models import Material, MaterialCategory, MaterialGroup, Unit
from san_xuat.forms import BomLineFormSet
from san_xuat.models import BomLine, BomVersion, ProductTechDoc
from san_xuat.services.bom_group import (
    dissolve_group_bom_lines,
    duplicate_material_codes,
    expand_bom_lines,
)
from san_xuat.services.bom_need import explode_bom, explode_overrides
from san_xuat.services.sales_orders import bom_lines_snapshot


def _cat():
    cat, _ = MaterialCategory.objects.get_or_create(code='zzt-chi', defaults={'name': 'Chi'})
    return cat


def _material(code, group=None, active=True):
    unit, _ = Unit.objects.get_or_create(code='zzt-cuon', defaults={'name': 'Cuon'})
    return Material.objects.create(
        code=code, name=code, category=_cat(), unit=unit, material_group=group, is_active=active,
    )


class BomMaterialGroupTests(TestCase):
    def setUp(self):
        self.group = MaterialGroup.objects.create(code='ZZT-CHI-MAY', name='Chi may', category=_cat())
        self.m1 = _material('ZZT-CHI-DO', self.group)
        self.m2 = _material('ZZT-CHI-XANH', self.group)
        self.m_off = _material('ZZT-CHI-CU', self.group, active=False)
        self.solo = _material('ZZT-NUT-01')
        self.doc = ProductTechDoc.objects.create(product_code='ZZT-SP-G', product_name='SP nhom')
        self.bom = BomVersion.objects.create(tech_doc=self.doc, version_label='v1')
        self.line_solo = BomLine.objects.create(bom=self.bom, material=self.solo, qty=Decimal('4'), sort_order=1)
        self.line_group = BomLine.objects.create(
            bom=self.bom, material_group=self.group, qty=Decimal('2'),
            scrap_pct=Decimal('10'), sort_order=2,
        )

    def test_constraint_requires_exactly_one(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BomLine.objects.create(bom=self.bom, qty=Decimal('1'))
        with transaction.atomic(), self.assertRaises(IntegrityError):
            BomLine.objects.create(bom=self.bom, material=self.solo, material_group=self.group, qty=Decimal('1'))

    def test_expand_gives_each_active_member_full_qty(self):
        items = expand_bom_lines(self.bom.lines.all())
        self.assertEqual([i.material.code for i in items], ['ZZT-NUT-01', 'ZZT-CHI-DO', 'ZZT-CHI-XANH'])
        by_code = {r.material_code: r for r in explode_bom(bom=self.bom, qty=Decimal('10'))}
        self.assertNotIn('ZZT-CHI-CU', by_code)
        self.assertEqual(by_code['ZZT-CHI-DO'].qty_total, Decimal('22.000'))
        self.assertEqual(by_code['ZZT-CHI-XANH'].qty_total, Decimal('22.000'))
        self.assertEqual(by_code['ZZT-NUT-01'].qty_total, Decimal('40.000'))

    def test_order_snapshot_expands_group_with_label(self):
        snap = bom_lines_snapshot(self.bom.pk)
        group_rows = [r for r in snap if r.get('material_group_id')]
        self.assertEqual({r['material_code'] for r in group_rows}, {'ZZT-CHI-DO', 'ZZT-CHI-XANH'})
        self.assertTrue(all(r['group_name'] == 'Chi may' for r in group_rows))
        self.assertTrue(all(r['bom_line_id'] == self.line_group.pk for r in group_rows))
        needs = explode_overrides(overrides=snap, qty=Decimal('10'))
        self.assertEqual(
            {n.material_code: n.qty_total for n in needs},
            {'ZZT-NUT-01': Decimal('40.000'), 'ZZT-CHI-DO': Decimal('22.000'), 'ZZT-CHI-XANH': Decimal('22.000')},
        )

    def test_snapshot_frozen_when_group_changes(self):
        snap = bom_lines_snapshot(self.bom.pk)
        _material('ZZT-CHI-VANG', self.group)
        needs = explode_overrides(overrides=snap, qty=Decimal('1'))
        self.assertNotIn('ZZT-CHI-VANG', {n.material_code for n in needs})
        self.assertIn('ZZT-CHI-VANG', {r.material_code for r in explode_bom(bom=self.bom, qty=Decimal('1'))})

    def test_duplicate_warning(self):
        self.assertEqual(duplicate_material_codes(self.bom), [])
        BomLine.objects.create(bom=self.bom, material=self.m1, qty=Decimal('1'), sort_order=3)
        self.assertEqual(duplicate_material_codes(self.bom), ['ZZT-CHI-DO'])

    def test_dissolve_before_group_delete(self):
        self.assertEqual(dissolve_group_bom_lines(self.group), 1)
        self.group.delete()
        lines = list(self.bom.lines.all())
        self.assertTrue(all(ln.material_id for ln in lines))
        self.assertEqual(
            sorted((ln.material.code, ln.qty) for ln in lines),
            [('ZZT-CHI-DO', Decimal('2.0000')), ('ZZT-CHI-XANH', Decimal('2.0000')), ('ZZT-NUT-01', Decimal('4.0000'))],
        )

    def _formset_data(self, material_value):
        return {
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-material': material_value,
            'lines-0-qty': '3',
            'lines-0-notes': '',
            'lines-0-sort_order': '1',
        }

    def test_formset_saves_group_line(self):
        bom = BomVersion.objects.create(tech_doc=self.doc, version_label='v2')
        fs = BomLineFormSet(self._formset_data(f'g:{self.group.pk}'), instance=bom, prefix='lines')
        self.assertTrue(fs.is_valid(), fs.errors)
        fs.save()
        line = bom.lines.get()
        self.assertIsNone(line.material_id)
        self.assertEqual(line.material_group_id, self.group.pk)

    def test_formset_rejects_empty_group(self):
        empty = MaterialGroup.objects.create(code='ZZT-RONG', name='Rong', category=_cat())
        bom = BomVersion.objects.create(tech_doc=self.doc, version_label='v3')
        fs = BomLineFormSet(self._formset_data(f'g:{empty.pk}'), instance=bom, prefix='lines')
        self.assertFalse(fs.is_valid())