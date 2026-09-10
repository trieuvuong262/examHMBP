from decimal import Decimal

from django.test import TestCase

from kho_npl.forms import MaterialForm, MaterialSpecificationForm
from kho_npl.models import (
    Material,
    MaterialCategory,
    MaterialSpecification,
    MaterialSpecificationLevel,
    StockBalance,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.uom import rebase_factor, rebase_price


class RebaseBasePriceTests(TestCase):
    def setUp(self):
        self.cat = MaterialCategory.objects.create(code='pk-test', name='Phu kien test')
        self.cai = Unit.objects.create(code='cai-t', name='Cai')
        self.bich = Unit.objects.create(code='bich-t', name='Bich')
        self.bao = Unit.objects.create(code='bao-t', name='Bao')
        self.spec_old = MaterialSpecification.objects.create(code='bich-only-t', name='Bich')
        MaterialSpecificationLevel.objects.create(
            specification=self.spec_old, level=1, unit=self.bich, qty_in_next_lower=Decimal('1'),
        )
        self.spec_new = MaterialSpecification.objects.create(
            code='bao-bich-cai-t', name='1bao=10bich, 1bich=1000c',
        )
        MaterialSpecificationLevel.objects.create(
            specification=self.spec_new, level=1, unit=self.cai, qty_in_next_lower=Decimal('1'),
        )
        MaterialSpecificationLevel.objects.create(
            specification=self.spec_new, level=2, unit=self.bich, qty_in_next_lower=Decimal('1000'),
        )
        MaterialSpecificationLevel.objects.create(
            specification=self.spec_new, level=3, unit=self.bao, qty_in_next_lower=Decimal('10'),
        )
        self.loc = WarehouseLocation.objects.create(code='MAIN-T', name='Main test')
        self.material = Material.objects.create(
            code='PK-HUTAM-T',
            name='HUT AM TEST',
            category=self.cat,
            specification=self.spec_old,
            unit=self.bich,
            min_stock=Decimal('10'),
            base_price=Decimal('49680'),
        )
        StockBalance.objects.create(
            material=self.material, location=self.loc, quantity=Decimal('13'),
        )

    def _form_data(self, **overrides):
        data = {
            'code': self.material.code,
            'name': self.material.name,
            'category': str(self.cat.pk),
            'specification': str(self.spec_old.pk),
            'min_stock': '10',
            'base_price': '49680',
            'price_qty_unit': str(self.bich.pk),
            'is_active': 'on',
            'variant_group': '',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_rebase_factor_old_package_to_piece(self):
        self.assertEqual(
            rebase_factor(self.bich, self.spec_new, old_specification=self.spec_old),
            Decimal('1000.000000'),
        )
        self.assertEqual(rebase_price(Decimal('49680'), Decimal('1000')), Decimal('49.680000'))

    def test_form_converts_base_price_to_odd_unit(self):
        form = MaterialForm(
            instance=self.material,
            data=self._form_data(specification=str(self.spec_new.pk)),
        )
        self.assertTrue(form.is_valid(), form.errors)
        material = form.save()
        material.refresh_from_db()
        self.assertEqual(material.unit_id, self.cai.pk)
        self.assertEqual(material.base_price, Decimal('49.680000'))
        self.assertEqual(material.min_stock, Decimal('10000.000'))
        self.assertEqual(
            StockBalance.objects.get(material=material).quantity,
            Decimal('13000.000'),
        )

    def test_js_already_converted_price_is_not_divided_again(self):
        form = MaterialForm(
            instance=self.material,
            data=self._form_data(
                specification=str(self.spec_new.pk),
                base_price='49.68',
                min_stock='10000',
                price_qty_unit=str(self.cai.pk),
            ),
        )
        self.assertTrue(form.is_valid(), form.errors)
        material = form.save()
        material.refresh_from_db()
        self.assertEqual(material.base_price, Decimal('49.680000'))
        self.assertEqual(material.min_stock, Decimal('10000.000'))

    def test_spec_form_rebases_materials_when_level1_changes(self):
        form = MaterialSpecificationForm(
            instance=self.spec_old,
            data={
                'code': self.spec_old.code,
                'name': '1bao=10bich, 1bich=2kg=1000c',
                'sort_order': '0',
                'is_active': 'on',
                'level1_unit': str(self.cai.pk),
                'level2_unit': str(self.bich.pk),
                'level2_qty': '1000',
                'level3_unit': str(self.bao.pk),
                'level3_qty': '10',
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.material.refresh_from_db()
        self.assertEqual(self.material.unit_id, self.cai.pk)
        self.assertEqual(self.material.base_price, Decimal('49.680000'))
        self.assertEqual(
            StockBalance.objects.get(material=self.material).quantity,
            Decimal('13000.000'),
        )
        levels = list(self.spec_old.levels.order_by('level').values_list('unit_id', 'qty_in_next_lower'))
        self.assertEqual(levels[0][0], self.cai.pk)
        self.assertEqual(levels[1], (self.bich.pk, Decimal('1000.000000')))
        self.assertEqual(levels[2], (self.bao.pk, Decimal('10.000000')))
