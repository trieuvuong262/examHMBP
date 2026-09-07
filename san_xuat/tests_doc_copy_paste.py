from datetime import date
from decimal import Decimal

from django.test import TestCase

from kho_npl.models import Material, MaterialCategory, Unit
from san_xuat.hub_models import SxProductionOrder
from san_xuat.ie_models import SxRouting, SxRoutingLine
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.tech_doc_copy import TechDocCopyError, paste_bom_and_ob


def _material(code):
    cat, _ = MaterialCategory.objects.get_or_create(code='vai', defaults={'name': 'Vải'})
    unit, _ = Unit.objects.get_or_create(code='m', defaults={'name': 'Mét'})
    return Material.objects.create(code=code, name=code, category=cat, unit=unit)


def _doc(code, name=''):
    return ProductTechDoc.objects.create(product_code=code, product_name=name or code)


def _bom(doc, label='v1', **kwargs):
    return BomVersion.objects.create(tech_doc=doc, version_label=label, **kwargs)


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


class PasteBomObTests(TestCase):
    def setUp(self):
        self.src = _doc('COPY-SRC', 'Ao nguon')
        self.dst = _doc('COPY-DST', 'Ao dich')
        self.mat_a = _material('NPL-A')
        self.mat_b = _material('NPL-B')

        self.src_bom = _bom(self.src, overhead_pct=Decimal('5'), notes='BOM nguon')
        BomLine.objects.create(bom=self.src_bom, material=self.mat_a, qty=Decimal('1.5'), scrap_pct=Decimal('2'))
        BomLine.objects.create(bom=self.src_bom, material=self.mat_b, qty=Decimal('0.2'), sort_order=1)

        self.src_rt = _routing(self.src)
        self.src_line = SxRoutingLine.objects.create(
            routing=self.src_rt,
            seq_no=10,
            op_code='CUT-01',
            op_name_vi='Cat',
            group_code='CUT',
            library_unit_smv=Decimal('12'),
            applied_unit_smv=Decimal('15'),
            notes='cat vai',
        )
        ProcessStep.objects.create(
            bom=self.src_bom,
            sequence=10,
            process_name='Cat',
            op_code='CUT-01',
            routing_line=self.src_line,
            norm_per_hour=Decimal('240'),
            cost_per_hour=Decimal('50000'),
            piece_rate=Decimal('1200'),
            std_time_minutes=Decimal('0.25'),
        )
        self.src_bom.routing = self.src_rt
        self.src_bom.save(update_fields=['routing'])

        self.dst_bom = _bom(self.dst, notes='BOM cu')
        BomLine.objects.create(bom=self.dst_bom, material=self.mat_b, qty=Decimal('9'))
        self.dst_rt = _routing(self.dst)
        SxRoutingLine.objects.create(
            routing=self.dst_rt,
            seq_no=1,
            op_code='OLD-01',
            op_name_vi='Cong doan cu',
            library_unit_smv=Decimal('1'),
            applied_unit_smv=Decimal('1'),
        )
        ProcessStep.objects.create(
            bom=self.dst_bom,
            sequence=1,
            process_name='Cu',
            norm_per_hour=Decimal('10'),
        )
        self.dst_bom.routing = self.dst_rt
        self.dst_bom.save(update_fields=['routing'])

    def test_paste_overwrites_bom_and_ob(self):
        result = paste_bom_and_ob(
            source_doc=self.src,
            source_bom=self.src_bom,
            source_routing=self.src_rt,
            target_doc=self.dst,
            target_bom=self.dst_bom,
            target_routing=self.dst_rt,
        )
        self.assertEqual(result.bom.pk, self.dst_bom.pk)
        self.assertEqual(result.routing.pk, self.dst_rt.pk)
        self.assertFalse(result.bom_new_version)
        self.assertFalse(result.routing_new_version)

        self.dst_bom.refresh_from_db()
        lines = list(self.dst_bom.lines.order_by('sort_order', 'id'))
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].material_id, self.mat_a.pk)
        self.assertEqual(lines[0].qty, Decimal('1.5'))
        self.assertEqual(self.dst_bom.overhead_pct, Decimal('5'))
        self.assertEqual(self.dst_bom.version_label, 'v1')

        ob_lines = list(self.dst_rt.lines.order_by('seq_no'))
        self.assertEqual(len(ob_lines), 1)
        self.assertEqual(ob_lines[0].op_code, 'CUT-01')
        self.assertEqual(ob_lines[0].applied_unit_smv, Decimal('15'))
        self.assertEqual(self.dst_rt.style_code, 'COPY-DST')

        steps = list(self.dst_bom.process_steps.order_by('sequence'))
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].process_name, 'Cat')
        self.assertEqual(steps[0].piece_rate, Decimal('1200'))
        self.assertEqual(steps[0].routing_line_id, ob_lines[0].pk)
        self.assertEqual(self.dst_bom.routing_id, self.dst_rt.pk)

    def test_rejects_same_doc(self):
        with self.assertRaises(TechDocCopyError):
            paste_bom_and_ob(
                source_doc=self.src,
                source_bom=self.src_bom,
                source_routing=self.src_rt,
                target_doc=self.src,
                target_bom=self.src_bom,
                target_routing=self.src_rt,
            )

    def test_locked_routing_creates_new_revision(self):
        SxProductionOrder.objects.create(
            code='MO-LOCK-1',
            product_code=self.dst.product_code,
            order_date=date(2026, 9, 1),
            routing=self.dst_rt,
        )
        old_pk = self.dst_rt.pk
        result = paste_bom_and_ob(
            source_doc=self.src,
            source_bom=self.src_bom,
            source_routing=self.src_rt,
            target_doc=self.dst,
            target_bom=self.dst_bom,
            target_routing=self.dst_rt,
        )
        self.assertTrue(result.routing_new_version)
        self.assertNotEqual(result.routing.pk, old_pk)
        self.assertTrue(self.dst_rt.lines.filter(op_code='OLD-01').exists())
        self.assertEqual(result.routing.lines.filter(op_code='CUT-01').count(), 1)
        self.dst_bom.refresh_from_db()
        self.assertEqual(self.dst_bom.routing_id, result.routing.pk)

    def test_locked_bom_creates_new_version(self):
        SxProductionOrder.objects.create(
            code='MO-LOCK-BOM',
            product_code=self.dst.product_code,
            order_date=date(2026, 9, 1),
            bom_version=self.dst_bom,
        )
        old_pk = self.dst_bom.pk
        result = paste_bom_and_ob(
            source_doc=self.src,
            source_bom=self.src_bom,
            source_routing=self.src_rt,
            target_doc=self.dst,
            target_bom=self.dst_bom,
            target_routing=self.dst_rt,
        )
        self.assertTrue(result.bom_new_version)
        self.assertNotEqual(result.bom.pk, old_pk)
        self.assertTrue(self.dst_bom.lines.filter(qty=Decimal('9')).exists())
        self.assertEqual(result.bom.lines.count(), 2)
