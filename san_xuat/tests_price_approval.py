"""Workflow duyet gia NPL."""
from __future__ import annotations
from decimal import Decimal
from django.test import TestCase
from kho_npl.models import Material, MaterialCategory, Supplier, Unit
from san_xuat.hub_models import (
    SxNplPurchaseRequest, SxNplPurchaseRequestLine, SxNplQuoteOffer, SxNplQuoteSheet,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services import price_approval as pa


def _row(mat, supplier_id, price, quality="OK", capacity="Du"):
    return {
        "material_id": mat.pk,
        "material_code": mat.code,
        "material_name": mat.name,
        "supplier_id": supplier_id,
        "unit_price": price,
        "quality_note": quality,
        "capacity_note": capacity,
    }


class PriceApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.s1 = Supplier.objects.create(code="NCC1", name="NCC 1")
        self.s2 = Supplier.objects.create(code="NCC2", name="NCC 2")
        self.s3 = Supplier.objects.create(code="NCC3", name="NCC 3")
        cat, _ = MaterialCategory.objects.get_or_create(code="vai", defaults={"name": "Vai"})
        unit, _ = Unit.objects.get_or_create(code="m", defaults={"name": "met"})
        self.m1 = Material.objects.create(code="VAI-01", name="Vai chinh", category=cat, unit=unit)
        self.m2 = Material.objects.create(code="CHI-01", name="Chi may", category=cat, unit=unit)

    def _sheet_with_three(self):
        sheet = pa.create_quote_sheet(title="Vai chinh")
        rows = [
            _row(self.m1, self.s1.pk, "100"),
            _row(self.m1, self.s2.pk, "95"),
            _row(self.m1, self.s3.pk, "98"),
        ]
        pa.save_quote_offers(sheet_id=sheet.pk, rows=rows)
        return sheet

    def test_submit_requires_three_suppliers(self):
        sheet = pa.create_quote_sheet()
        pa.save_quote_offers(sheet_id=sheet.pk, rows=[
            _row(self.m1, self.s1.pk, "100"),
            _row(self.m1, self.s2.pk, "95"),
        ])
        with self.assertRaises(PlanningError):
            pa.submit_quote_sheet(sheet_id=sheet.pk)

    def test_submit_requires_material_in_warehouse(self):
        sheet = pa.create_quote_sheet()
        with self.assertRaises(PlanningError):
            pa.save_quote_offers(sheet_id=sheet.pk, rows=[{
                "material_code": "NO-SUCH",
                "supplier_id": self.s1.pk,
                "unit_price": "100",
                "quality_note": "OK",
                "capacity_note": "Du",
            }])

    def test_submit_requires_quality_and_capacity(self):
        sheet = pa.create_quote_sheet()
        pa.save_quote_offers(sheet_id=sheet.pk, rows=[
            _row(self.m1, self.s1.pk, "100", quality="", capacity="Du"),
            _row(self.m1, self.s2.pk, "95"),
            _row(self.m1, self.s3.pk, "98"),
        ])
        with self.assertRaises(PlanningError):
            pa.submit_quote_sheet(sheet_id=sheet.pk)

    def test_submit_requires_positive_price(self):
        sheet = pa.create_quote_sheet()
        pa.save_quote_offers(sheet_id=sheet.pk, rows=[
            _row(self.m1, self.s1.pk, "0"),
            _row(self.m1, self.s2.pk, "95"),
            _row(self.m1, self.s3.pk, "98"),
        ])
        with self.assertRaises(PlanningError):
            pa.submit_quote_sheet(sheet_id=sheet.pk)

    def test_decide_marks_single_offer_chosen(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        chosen = sheet.offers.get(supplier=self.s2)
        pa.decide_quote_sheet(sheet_id=sheet.pk, chosen_ids=[chosen.pk])
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, SxNplQuoteSheet.STATUS_DECIDED)
        self.assertEqual(sheet.offers.filter(is_chosen=True).count(), 1)
        offer = sheet.offers.get(supplier=self.s2)
        self.assertTrue(offer.is_chosen)
        self.assertEqual(offer.material_id, self.m1.pk)

    def test_decide_rejects_two_offers_same_material(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        ids = [o.pk for o in sheet.offers.all()[:2]]
        with self.assertRaises(PlanningError):
            pa.decide_quote_sheet(sheet_id=sheet.pk, chosen_ids=ids)

    def test_decide_requires_every_material(self):
        sheet = pa.create_quote_sheet()
        pa.save_quote_offers(sheet_id=sheet.pk, rows=[
            _row(self.m1, self.s1.pk, "100"),
            _row(self.m1, self.s2.pk, "95"),
            _row(self.m1, self.s3.pk, "98"),
            _row(self.m2, self.s1.pk, "10"),
            _row(self.m2, self.s2.pk, "11"),
        ])
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        only_vai = sheet.offers.get(material=self.m1, supplier=self.s2)
        with self.assertRaises(PlanningError):
            pa.decide_quote_sheet(sheet_id=sheet.pk, chosen_ids=[only_vai.pk])

    def test_return_quote_sheet_to_draft(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        pa.return_quote_sheet(sheet_id=sheet.pk)
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, SxNplQuoteSheet.STATUS_DRAFT)

    def test_save_blocked_while_submitted(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        with self.assertRaises(PlanningError):
            pa.save_quote_offers(sheet_id=sheet.pk, rows=[_row(self.m1, self.s1.pk, "100")])

    def _decided_offer(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        chosen = sheet.offers.get(supplier=self.s2)
        pa.decide_quote_sheet(sheet_id=sheet.pk, chosen_ids=[chosen.pk])
        return SxNplQuoteOffer.objects.get(pk=chosen.pk)

    def _pr_with_chosen_line(self, offer):
        pr = SxNplPurchaseRequest.objects.create(code="DDH-T1", is_demo=False)
        SxNplPurchaseRequestLine.objects.create(
            request=pr, material_code=offer.material_code, qty=Decimal("10"),
            supplier=offer.supplier, unit_price=offer.unit_price, quote_offer=offer,
        )
        return pr

    def test_price_review_happy_path(self):
        offer = self._decided_offer()
        pr = self._pr_with_chosen_line(offer)
        pa.submit_price_review(request_id=pr.pk)
        pr.refresh_from_db()
        self.assertEqual(pr.status, SxNplPurchaseRequest.STATUS_PRICE_REVIEW)
        pa.approve_price_review(request_id=pr.pk)
        pr.refresh_from_db()
        self.assertEqual(pr.status, SxNplPurchaseRequest.STATUS_PRICED)

    def test_price_review_blocks_price_mismatch(self):
        offer = self._decided_offer()
        pr = self._pr_with_chosen_line(offer)
        line = pr.lines.first()
        line.unit_price = Decimal("1")
        line.save(update_fields=["unit_price"])
        with self.assertRaises(PlanningError):
            pa.submit_price_review(request_id=pr.pk)

    def test_price_review_blocks_unchosen_offer(self):
        sheet = self._sheet_with_three()
        pa.submit_quote_sheet(sheet_id=sheet.pk)
        not_chosen = sheet.offers.get(supplier=self.s1)
        pa.decide_quote_sheet(sheet_id=sheet.pk, chosen_ids=[sheet.offers.get(supplier=self.s2).pk])
        pr = self._pr_with_chosen_line(SxNplQuoteOffer.objects.get(pk=not_chosen.pk))
        with self.assertRaises(PlanningError):
            pa.submit_price_review(request_id=pr.pk)

    def test_return_price_review_goes_back_to_draft(self):
        offer = self._decided_offer()
        pr = self._pr_with_chosen_line(offer)
        pa.submit_price_review(request_id=pr.pk)
        pa.return_price_review(request_id=pr.pk, note="Gia cao")
        pr.refresh_from_db()
        self.assertEqual(pr.status, SxNplPurchaseRequest.STATUS_DRAFT)
