"""Smoke tests — man in phieu A5 (P0 + P1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxNcrCase,
    SxPackingRecord,
    SxProductionOrder,
    SxQcAlert,
    SxQcInspection,
    SxSubcontractMaterialLine,
    SxSubcontractOrder,
    SxWipHandover,
)
from san_xuat.print_company import COMPANY_NAME, COMPANY_TAX_CODE


class SanXuatPrintA5Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("sx_print_admin", "print@test.local", "x")
        today = date(2026, 7, 21)
        cls.mo = SxProductionOrder.objects.create(
            code="LSX-PRINT-001",
            product_code="SP-PRINT",
            product_name="San pham in test",
            qty=Decimal("100"),
            qty_done=Decimal("0"),
            order_date=today,
            status=SxProductionOrder.STATUS_RELEASED,
            team_label="To A",
        )
        cls.ycx = SxMaterialIssueRequest.objects.create(
            code="YCX-PRINT-001",
            production_order=cls.mo,
            status="draft",
            request_date=today,
        )
        cls.ycntp = SxFgReceiptRequest.objects.create(
            code="YCNTP-PRINT-001",
            production_order=cls.mo,
            request_date=today,
            qty=Decimal("50"),
            status=SxFgReceiptRequest.STATUS_DRAFT,
        )
        cls.handover = SxWipHandover.objects.create(
            code="BG-PRINT-001",
            production_order=cls.mo,
            from_process="Cat",
            to_process="May",
            qty=Decimal("20"),
            handover_date=today,
            status=SxWipHandover.STATUS_PENDING,
        )
        cls.inspection = SxQcInspection.objects.create(
            code="PKT-PRINT-001",
            inspected_at=today,
            qty_sample=Decimal("5"),
            qty_pass=Decimal("5"),
            qty_fail=Decimal("0"),
            result=SxQcInspection.RESULT_PASS,
            status="done",
        )
        cls.alert = SxQcAlert.objects.create(
            code="CBQC-PRINT-001",
            alert_type=SxQcAlert.TYPE_DEFECT_RATE,
            production_order=cls.mo,
            process_name="May",
            defect_rate=Decimal("8"),
            tolerance_limit=Decimal("5"),
            qty_good=Decimal("92"),
            qty_defect=Decimal("8"),
            message="Ty le loi vuot nguong (test)",
            status=SxQcAlert.STATUS_OPEN,
        )
        cls.packing = SxPackingRecord.objects.create(
            code="DG-PRINT-001",
            production_order=cls.mo,
            pack_date=today,
            qty=Decimal("40"),
            carton_count=4,
            lot_code="LO-PRINT-001",
            status=SxPackingRecord.STATUS_CONFIRMED,
        )
        cls.subcontract = SxSubcontractOrder.objects.create(
            code="GC-PRINT-001",
            production_order=cls.mo,
            vendor_name="NCC Test GC",
            product_code=cls.mo.product_code,
            product_name=cls.mo.product_name,
            process_name="Theu",
            qty=Decimal("30"),
            order_date=today,
            status=SxSubcontractOrder.STATUS_DRAFT,
        )
        SxSubcontractMaterialLine.objects.create(
            order=cls.subcontract,
            direction=SxSubcontractMaterialLine.DIRECTION_OUT,
            material_code="NPL-01",
            material_name="Vai test",
            qty=Decimal("10"),
        )
        cls.ncr = SxNcrCase.objects.create(
            code="NCR-PRINT-001",
            production_order=cls.mo,
            alert=cls.alert,
            disposition=SxNcrCase.DISP_REWORK,
            qty=Decimal("8"),
            process_name="May",
            status=SxNcrCase.STATUS_DRAFT,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="testserver")
        self.client.force_login(self.user)

    def _assert_print_ok(self, url_name, pk, *must_contain):
        url = reverse(f"san_xuat:{url_name}", args=[pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=f"{url_name} -> {resp.status_code}")
        body = resp.content.decode("utf-8")
        self.assertIn(COMPANY_TAX_CODE, body)
        self.assertIn(COMPANY_NAME, body)
        self.assertIn("A5", body)
        self.assertIn("Ky, ho ten".replace("Ky, ho ten", "Ký, họ tên"), body)
        for fragment in must_contain:
            self.assertIn(fragment, body, msg=f"{url_name} missing {fragment!r}")

    def test_print_p0_pages(self):
        self._assert_print_ok("print_mo", self.mo.pk, self.mo.code, "Lệnh sản xuất")
        self._assert_print_ok("print_ycx", self.ycx.pk, self.ycx.code, "Yêu cầu xuất vật tư")
        self._assert_print_ok("print_qc", self.inspection.pk, self.inspection.code, "Phiếu kiểm tra")
        self._assert_print_ok("print_packing", self.packing.pk, self.packing.code, "Phiếu đóng gói")

    def test_print_p1_pages(self):
        self._assert_print_ok("print_ycntp", self.ycntp.pk, self.ycntp.code, "Yêu cầu nhập thành phẩm")
        self._assert_print_ok("print_handover", self.handover.pk, self.handover.code, "Bàn giao")
        self._assert_print_ok("print_subcontract", self.subcontract.pk, self.subcontract.code, "Thuê gia công")
        self._assert_print_ok("print_ncr", self.ncr.pk, self.ncr.code, "NCR")
        self._assert_print_ok("print_qc_alert", self.alert.pk, self.alert.code, "Cảnh báo")

    def test_print_urls_registered(self):
        names = [
            "print_mo", "print_ycx", "print_qc", "print_packing",
            "print_ycntp", "print_handover", "print_subcontract",
            "print_ncr", "print_qc_alert",
        ]
        for name in names:
            self.assertTrue(reverse(f"san_xuat:{name}", args=[1]).endswith("/in/"))
