
from datetime import date
from decimal import Decimal

from django.test import TestCase

from kho_npl.models import Material, MaterialCategory, Unit
from san_xuat.ie_models import SxRouting, SxRoutingLine
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.order_routing import (
    apply_smv_overrides,
    process_preview_from_bom,
    seed_order_line_routing,
)
from san_xuat.services.sales_orders import (
    LineInput,
    _normalize_bom_overrides,
    create_sales_order,
    merge_bom_overrides,
    update_sales_order,
)


def _material(code):
    cat, _ = MaterialCategory.objects.get_or_create(code='vai', defaults={'name': 'Vải'})
    unit, _ = Unit.objects.get_or_create(code='m', defaults={'name': 'Mét'})
    return Material.objects.create(code=code, name=code, category=cat, unit=unit)


def _doc(code, name=''):
    return ProductTechDoc.objects.create(product_code=code, product_name=name or code)


def _routing(doc, rev='R01'):
    code = doc.product_code
    return SxRouting.objects.create(
        routing_id=f'{code}-{rev}',
        style_code=code,
        style_name=doc.product_name,
        routing_rev=rev,
        tech_doc=doc,
        is_active=True,
    )


class OrderSmvOverrideStabilityTests(TestCase):
    def setUp(self):
        self.doc = _doc('JP-SMV-1', 'Ao test SMV')
        self.rt = _routing(self.doc)
        SxRoutingLine.objects.create(
            routing=self.rt,
            seq_no=10,
            op_code='CUT-01',
            op_name_vi='Cat',
            library_unit_smv=Decimal('10'),
            applied_unit_smv=Decimal('10'),
        )
        SxRoutingLine.objects.create(
            routing=self.rt,
            seq_no=20,
            op_code='SEW-01',
            op_name_vi='May',
            library_unit_smv=Decimal('20'),
            applied_unit_smv=Decimal('20'),
        )

    def test_override_follows_op_code_when_seq_changes(self):
        order = create_sales_order(
            customer_name='KH',
            request_date=date(2026, 9, 10),
            lines=[LineInput(
                product_code=self.doc.product_code,
                qty=Decimal('2'),
                routing_id=self.rt.pk,
                applied_smv=[{
                    'seq': 10,
                    'op_code': 'CUT-01',
                    'smv': 12,
                    'smv_pct': 120,
                    'smv_mode': 'pct',
                }],
            )],
        )
        ln = order.lines.get()
        cut = ln.routing_lines.get(op_code='CUT-01')
        sew = ln.routing_lines.get(op_code='SEW-01')
        self.assertEqual(cut.applied_unit_smv, Decimal('12.0000'))
        self.assertEqual(sew.applied_unit_smv, Decimal('20.0000'))

        cut.seq_no = 99
        cut.save(update_fields=['seq_no'])
        sew.seq_no = 10
        sew.save(update_fields=['seq_no'])
        cut.seq_no = 20
        cut.save(update_fields=['seq_no'])

        apply_smv_overrides(ln, [{
            'seq': 10,
            'op_code': 'CUT-01',
            'smv': 12,
            'smv_pct': 120,
            'smv_mode': 'pct',
        }])
        cut.refresh_from_db()
        sew.refresh_from_db()
        self.assertEqual(cut.applied_unit_smv, Decimal('12.0000'))
        self.assertEqual(sew.applied_unit_smv, Decimal('20.0000'))

    def test_op_code_override_does_not_land_on_other_seq(self):
        order = create_sales_order(
            customer_name='KH',
            request_date=date(2026, 9, 10),
            lines=[LineInput(
                product_code=self.doc.product_code,
                qty=Decimal('1'),
                routing_id=self.rt.pk,
            )],
        )
        ln = order.lines.get()
        n = apply_smv_overrides(ln, [{
            'seq': 10,
            'op_code': 'SEW-01',
            'smv': 40,
            'smv_pct': 200,
            'smv_mode': 'pct',
        }])
        self.assertEqual(n, 1)
        cut = ln.routing_lines.get(op_code='CUT-01')
        sew = ln.routing_lines.get(op_code='SEW-01')
        self.assertEqual(cut.applied_unit_smv, Decimal('10.0000'))
        self.assertEqual(sew.applied_unit_smv, Decimal('40.0000'))

    def test_update_order_keeps_smv_on_same_ops_after_reorder(self):
        order = create_sales_order(
            customer_name='KH',
            request_date=date(2026, 9, 10),
            lines=[LineInput(
                product_code=self.doc.product_code,
                qty=Decimal('3'),
                routing_id=self.rt.pk,
                applied_smv=[{
                    'seq': 10,
                    'op_code': 'CUT-01',
                    'smv': 15,
                    'smv_pct': 150,
                    'smv_mode': 'pct',
                }],
            )],
        )
        self.rt.lines.filter(op_code='CUT-01').update(seq_no=30)
        self.rt.lines.filter(op_code='SEW-01').update(seq_no=10)
        SxRoutingLine.objects.create(
            routing=self.rt,
            seq_no=20,
            op_code='PACK-01',
            op_name_vi='Dong',
            library_unit_smv=Decimal('5'),
            applied_unit_smv=Decimal('5'),
        )
        update_sales_order(
            order_id=order.pk,
            customer_name='KH',
            request_date=date(2026, 9, 10),
            lines=[LineInput(
                product_code=self.doc.product_code,
                qty=Decimal('3'),
                routing_id=self.rt.pk,
                applied_smv=[{
                    'seq': 10,
                    'op_code': 'CUT-01',
                    'smv': 15,
                    'smv_pct': 150,
                    'smv_mode': 'pct',
                }],
            )],
        )
        ln = order.lines.get()
        self.assertEqual(ln.routing_lines.get(op_code='CUT-01').applied_unit_smv, Decimal('15.0000'))
        self.assertEqual(ln.routing_lines.get(op_code='SEW-01').applied_unit_smv, Decimal('20.0000'))
        self.assertEqual(ln.routing_lines.get(op_code='PACK-01').applied_unit_smv, Decimal('5.0000'))


class BomPreviewSeqAndQtyTests(TestCase):
    def setUp(self):
        self.doc = _doc('JP-BOM-1', 'Ao BOM')
        self.bom = BomVersion.objects.create(tech_doc=self.doc, version_label='v1')
        ProcessStep.objects.create(bom=self.bom, sequence=0, process_name='Cat', op_code='CUT-01', norm_per_hour=Decimal('60'), std_time_minutes=Decimal('1'))
        ProcessStep.objects.create(bom=self.bom, sequence=0, process_name='May', op_code='SEW-01', norm_per_hour=Decimal('60'), std_time_minutes=Decimal('1'))
        self.mat = _material('NPL-SMV-A')
        BomLine.objects.create(bom=self.bom, material=self.mat, qty=Decimal('0.125'))

    def test_preview_assigns_unique_seq_when_sequence_is_zero(self):
        steps = process_preview_from_bom(self.bom)
        seqs = [s['seq'] for s in steps]
        self.assertEqual(len(seqs), 2)
        self.assertEqual(len(set(seqs)), 2)
        self.assertTrue(all(s > 0 for s in seqs))

    def test_seed_seq_matches_preview_when_sequence_duplicates(self):
        order = create_sales_order(
            customer_name='KH',
            request_date=date(2026, 9, 10),
            lines=[LineInput(
                product_code=self.doc.product_code,
                qty=Decimal('1'),
                bom_version_id=self.bom.pk,
            )],
        )
        ln = order.lines.get()
        seed_order_line_routing(ln, replace=True)
        preview = process_preview_from_bom(self.bom)
        snap_seqs = list(ln.routing_lines.order_by('seq_no').values_list('seq_no', flat=True))
        self.assertEqual(snap_seqs, [s['seq'] for s in preview])

    def test_bom_qty_keeps_four_decimals(self):
        rows = _normalize_bom_overrides([{
            'bom_line_id': 1,
            'material_code': 'NPL-SMV-A',
            'qty_std': 0.125,
            'qty': 0.125,
            'qty_pct': 100,
            'qty_mode': 'qty',
        }])
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0]['qty'])), Decimal('0.1250'))
        self.assertEqual(Decimal(str(rows[0]['qty_std'])), Decimal('0.1250'))

    def test_merge_bom_keeps_pct_by_material_when_line_id_changes(self):
        fresh = [{
            'bom_line_id': 99,
            'material_code': 'NPL-SMV-A',
            'material_name': 'Vai',
            'qty': 0.2,
            'qty_std': 0.2,
            'qty_pct': 100.0,
            'qty_mode': 'pct',
            'size_code': '',
            'scrap_pct': 0,
            'unit': 'm',
        }]
        previous = [{
            'bom_line_id': 1,
            'material_code': 'NPL-SMV-A',
            'qty': 0.15,
            'qty_std': 0.125,
            'qty_pct': 120,
            'qty_mode': 'pct',
            'size_code': '',
        }]
        merged = merge_bom_overrides(fresh, previous)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['qty_pct'], 120.0)
        self.assertEqual(Decimal(str(merged[0]['qty'])), Decimal('0.2400'))
        self.assertEqual(merged[0]['bom_line_id'], 99)
