from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from san_xuat.partner_models import GcOutputReport, GcPartner, GcPartnerAccount
from san_xuat.partner_portal import auth
from san_xuat.services.gc_output import approve_report, unapprove_report
from san_xuat.hub_models import SxSubcontractOrder


@override_settings(MIDDLEWARE=[m for m in __import__('PortalJustPlay.settings', fromlist=['MIDDLEWARE']).MIDDLEWARE if m != 'audit.middleware_spam.SpamIpGuardMiddleware'])
class PartnerPortalSmokeTests(TestCase):
    host = "pn.localhost:8000"

    def setUp(self):
        self.partner = GcPartner.objects.create(code="TEST-GC", name="Đối tác test")
        self.account = GcPartnerAccount(
            partner=self.partner, username="owner-test", role=GcPartnerAccount.ROLE_OWNER,
            must_change_password=False,
        )
        self.account.set_password("TestPass123")
        self.account.save()
        self.order = SxSubcontractOrder.objects.create(
            code="GC-SMOKE-001", partner=self.partner, vendor_name=self.partner.name,
            product_code="SP-SMOKE", product_name="Sản phẩm test", process_name="May",
            team_slug="may", qty=Decimal("100"), order_date=date.today(),
            status=SxSubcontractOrder.STATUS_SENT,
        )

    def test_partner_login_and_owner_kpi_are_host_isolated(self):
        response = self.client.get("/", HTTP_HOST=self.host)
        self.assertRedirects(response, "/dang-nhap/?next=/", fetch_redirect_response=False)

        response = self.client.post(
            "/dang-nhap/", {"username": "owner-test", "password": "TestPass123"},
            HTTP_HOST=self.host,
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertIsNotNone(self.client.session.get(auth.SESSION_KEY))

        response = self.client.get("/bao-cao/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thống kê")



    def test_report_requires_acceptance_and_never_exceeds_order_qty(self):
        self.client.post(
            "/dang-nhap/", {"username": "owner-test", "password": "TestPass123"},
            HTTP_HOST=self.host,
        )
        response = self.client.post(
            f"/don/{self.order.pk}/",
            {"action": "report", "work_date": date.today().isoformat(), "size_M": "10"},
            HTTP_HOST=self.host, follow=True,
        )
        self.assertContains(response, "Nhận đơn", status_code=200)
        self.client.post(f"/don/{self.order.pk}/", {"action": "accept"}, HTTP_HOST=self.host)

        self.client.post(
            f"/don/{self.order.pk}/",
            {"action": "report", "work_date": date.today().isoformat(), "size_M": "100"},
            HTTP_HOST=self.host,
        )
        response = self.client.post(
            f"/don/{self.order.pk}/",
            {"action": "report", "work_date": date.today().isoformat(), "size_M": "1"},
            HTTP_HOST=self.host, follow=True,
        )
        self.assertContains(response, "Vượt SL phiếu", status_code=200)
        self.assertEqual(GcOutputReport.objects.filter(order=self.order).count(), 1)

    def test_qc_approve_and_unapprove_preserve_report_state(self):
        self.client.post(
            "/dang-nhap/", {"username": "owner-test", "password": "TestPass123"},
            HTTP_HOST=self.host,
        )
        self.client.post(f"/don/{self.order.pk}/", {"action": "accept"}, HTTP_HOST=self.host)
        self.client.post(
            f"/don/{self.order.pk}/",
            {"action": "report", "work_date": date.today().isoformat(), "size_M": "25"},
            HTTP_HOST=self.host,
        )
        report = GcOutputReport.objects.get(order=self.order)
        staff = get_user_model().objects.create_user(username="qc-smoke", password="TestPass123")

        report = approve_report(report_id=report.pk, user=staff, size_qtys={"M": "20"})
        self.assertEqual(report.status, GcOutputReport.STATUS_APPROVED)
        self.assertEqual(report.approved_qty, Decimal("20.00"))
        self.assertEqual(report.progress_posted, {})

        report = unapprove_report(report_id=report.pk, user=staff)
        self.assertEqual(report.status, GcOutputReport.STATUS_SUBMITTED)
        self.assertEqual(report.approved_qty, Decimal("0.00"))
