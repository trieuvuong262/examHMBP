from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxSubcontractOrder
from san_xuat.partner_models import (
    GcKpiSnapshot,
    GcOutputReport,
    GcPartner,
    GcPartnerAccount,
    GcPartnerActivity,
)
from san_xuat.partner_portal import auth
from san_xuat.services.gc_kpi import grade_for, kpi_for_display, kpi_score, lock_kpi
from san_xuat.services.gc_output import (
    GcOutputError,
    approve_report,
    recall_from_partner,
    send_to_partner,
    unapprove_report,
)

_MIDDLEWARE = [
    m for m in __import__('PortalJustPlay.settings', fromlist=['MIDDLEWARE']).MIDDLEWARE
    if m != 'audit.middleware_spam.SpamIpGuardMiddleware'
]
HOST = 'pn.localhost:8000'


def _account(partner, username, role):
    acc = GcPartnerAccount(partner=partner, username=username, role=role, must_change_password=False)
    acc.set_password('TestPass123')
    acc.save()
    return acc


@override_settings(MIDDLEWARE=_MIDDLEWARE)
class PartnerPortalFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.partner = GcPartner.objects.create(code='TEST-GC', name='Đối tác test')
        self.owner = _account(self.partner, 'owner-test', GcPartnerAccount.ROLE_OWNER)
        self.staff = _account(self.partner, 'staff-test', GcPartnerAccount.ROLE_STAFF)
        self.mo = SxProductionOrder.objects.create(
            code='LSX-PN-001', product_code='SP-SMOKE', product_name='Sản phẩm test',
            qty=Decimal('100'), order_date=date.today(), status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        self.order = SxSubcontractOrder.objects.create(
            code='GC-SMOKE-001', partner=self.partner, vendor_name=self.partner.name,
            product_code='SP-SMOKE', product_name='Sản phẩm test', process_name='May',
            team_slug='may', qty=Decimal('100'), unit_price=Decimal('1000'),
            order_date=date.today(), status=SxSubcontractOrder.STATUS_DRAFT,
            production_order=self.mo,
        )
        self.user = get_user_model().objects.create_user(username='qc-smoke', password='TestPass123')

    def _login(self, username='owner-test'):
        response = self.client.post(
            '/dang-nhap/', {'username': username, 'password': 'TestPass123'}, HTTP_HOST=HOST,
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def _post(self, data, follow=False):
        return self.client.post(f'/don/{self.order.pk}/', data, HTTP_HOST=HOST, follow=follow)

    def _report(self, qty, size='Tổng'):
        return self._post({'action': 'report', 'work_date': date.today().isoformat(), f'size_{size}': str(qty)})

    # --- Gửi đối tác -----------------------------------------------------

    def test_order_hidden_until_sent_and_send_requires_lsx(self):
        self._login()
        self.assertEqual(self.client.get(f'/don/{self.order.pk}/', HTTP_HOST=HOST).status_code, 404)

        no_lsx = SxSubcontractOrder.objects.create(
            code='GC-NO-LSX', partner=self.partner, vendor_name='x', product_code='SP',
            team_slug='may', qty=Decimal('5'), order_date=date.today(),
        )
        with self.assertRaises(GcOutputError):
            send_to_partner(order_id=no_lsx.pk, user=self.user)

        send_to_partner(order_id=self.order.pk, user=self.user)
        self.assertEqual(self.client.get(f'/don/{self.order.pk}/', HTTP_HOST=HOST).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.partner_sent_by, self.user)

        recall_from_partner(order_id=self.order.pk)
        self.assertEqual(self.client.get(f'/don/{self.order.pk}/', HTTP_HOST=HOST).status_code, 404)

    def test_other_partner_cannot_open_order(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        other = GcPartner.objects.create(code='OTHER', name='Khác')
        _account(other, 'other-owner', GcPartnerAccount.ROLE_OWNER)
        self._login('other-owner')
        self.assertEqual(self.client.get(f'/don/{self.order.pk}/', HTTP_HOST=HOST).status_code, 404)
        self.assertNotContains(self.client.get('/?tab=all', HTTP_HOST=HOST), self.order.code)

    # --- Nhận / từ chối --------------------------------------------------

    def test_only_owner_accepts_and_staff_reports_after_accept(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login('staff-test')
        self._post({'action': 'accept'})
        self.order.refresh_from_db()
        self.assertIsNone(self.order.partner_accepted_at)
        response = self._post(
            {'action': 'report', 'work_date': date.today().isoformat(), 'size_Tổng': '5'}, follow=True,
        )
        self.assertContains(response, 'Nhận đơn')
        self.assertFalse(GcOutputReport.objects.exists())
        self.assertNotContains(self.client.get('/', HTTP_HOST=HOST), '/bao-cao/')

        self.client.post('/dang-xuat/', HTTP_HOST=HOST)
        self._login('owner-test')
        self._post({'action': 'accept'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.partner_accepted_by, self.owner)
        self.assertTrue(GcPartnerActivity.objects.filter(action=GcPartnerActivity.ACTION_ACCEPT).exists())

        self.client.post('/dang-xuat/', HTTP_HOST=HOST)
        self._login('staff-test')
        self._report(5)
        self.assertEqual(GcOutputReport.objects.get().account, self.staff)

    def test_reject_requires_reason_and_removes_order_from_portal(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login()
        self._post({'action': 'reject', 'reason': ''})
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.partner_sent_at)

        self._post({'action': 'reject', 'reason': 'Hết năng lực tháng này'})
        self.order.refresh_from_db()
        self.assertIsNone(self.order.partner_sent_at)
        self.assertEqual(self.order.partner_state, 'rejected')
        self.assertEqual(self.order.partner_reject_reason, 'Hết năng lực tháng này')
        self.assertEqual(self.client.get(f'/don/{self.order.pk}/', HTTP_HOST=HOST).status_code, 404)

        send_to_partner(order_id=self.order.pk, user=self.user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.partner_state, 'waiting')
        self.assertEqual(self.order.partner_reject_reason, '')

    # --- Báo sản lượng ---------------------------------------------------

    def test_over_report_allowed_and_paid_on_approved_qty(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login()
        self._post({'action': 'accept'})
        self._report(100)
        self._report(30)
        self.assertEqual(GcOutputReport.objects.filter(order=self.order).count(), 2)
        self._post({'action': 'report', 'work_date': date.today().isoformat(), 'size_XXL-FAKE': '9'})
        self.assertEqual(GcOutputReport.objects.filter(order=self.order).count(), 2)

        for report in GcOutputReport.objects.filter(order=self.order).order_by('pk'):
            approve_report(report_id=report.pk, user=self.user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.qty_received, Decimal('130.00'))
        self.assertEqual(self.order.service_fee, Decimal('130000.00'))

    def test_cancel_report_keeps_record(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login()
        self._post({'action': 'accept'})
        self._report(10)
        report = GcOutputReport.objects.get()
        self._post({'action': 'cancel_report', 'report_id': report.pk})
        report.refresh_from_db()
        self.assertEqual(report.status, GcOutputReport.STATUS_CANCELLED)
        self.assertEqual(report.cancelled_by, self.owner)
        with self.assertRaises(GcOutputError):
            approve_report(report_id=report.pk, user=self.user)

    def test_qc_approve_and_unapprove_preserve_report_state(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login()
        self._post({'action': 'accept'})
        self._report(25)
        report = GcOutputReport.objects.get(order=self.order)

        report = approve_report(report_id=report.pk, user=self.user, size_qtys={'Tổng': '20'})
        self.assertEqual(report.status, GcOutputReport.STATUS_APPROVED)
        self.assertEqual(report.approved_qty, Decimal('20.00'))

        report = unapprove_report(report_id=report.pk, user=self.user)
        self.assertEqual(report.status, GcOutputReport.STATUS_SUBMITTED)
        self.assertEqual(report.approved_qty, Decimal('0.00'))

    # --- Đăng nhập -------------------------------------------------------

    def test_login_errors_are_generic_and_logged(self):
        response = self.client.post(
            '/dang-nhap/', {'username': 'khong-ton-tai', 'password': 'x'}, HTTP_HOST=HOST,
        )
        unknown_msg = response.context['error']
        for _ in range(auth.MAX_FAILED):
            self.client.post('/dang-nhap/', {'username': 'owner-test', 'password': 'sai'}, HTTP_HOST=HOST)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_locked)
        response = self.client.post(
            '/dang-nhap/', {'username': 'owner-test', 'password': 'TestPass123'}, HTTP_HOST=HOST,
        )
        self.assertEqual(response.context['error'], unknown_msg)
        self.assertTrue(
            GcPartnerActivity.objects.filter(action=GcPartnerActivity.ACTION_LOGIN_FAILED, account=self.owner).exists()
        )

    # --- KPI -------------------------------------------------------------

    def test_owner_kpi_page_and_lock_snapshot(self):
        send_to_partner(order_id=self.order.pk, user=self.user)
        self._login()
        self._post({'action': 'accept'})
        self._report(50)
        approve_report(report_id=GcOutputReport.objects.get().pk, user=self.user, size_qtys={'Tổng': '40'})

        response = self.client.get('/bao-cao/', HTTP_HOST=HOST)
        self.assertContains(response, 'Tạm tính')
        self.assertContains(response, 'Chất lượng')
        self.assertEqual(self.client.get('/bang-gia/', HTTP_HOST=HOST).status_code, 200)

        month = timezone.localdate().strftime('%Y-%m')
        kpi = kpi_for_display(self.partner, month=month)
        self.assertEqual(kpi['pass_rate'], Decimal('80.0'))
        self.assertEqual(kpi['response_rate'], Decimal('100.0'))
        snap = lock_kpi(partner=self.partner, month=month, user=self.user)
        self.assertEqual(snap.score, kpi['score'])

        # Dữ liệu sửa sau khi chốt không đổi KPI đã chốt.
        GcOutputReport.objects.update(approved_qty=Decimal('50'))
        locked = kpi_for_display(self.partner, month=month)
        self.assertTrue(locked['locked'])
        self.assertEqual(locked['approved'], Decimal('40'))
        self.assertEqual(GcKpiSnapshot.objects.count(), 1)


class GcKpiScoreTests(SimpleTestCase):
    def test_weights_and_missing_criteria(self):
        self.assertEqual(
            kpi_score({'quality': Decimal('100'), 'on_time': Decimal('100'), 'plan': Decimal('100'), 'response': Decimal('100')}),
            Decimal('100.0'),
        )
        # 40×90 + 30×80 + 20×50 + 10×0 = 7000 / 100
        self.assertEqual(
            kpi_score({'quality': Decimal('90'), 'on_time': Decimal('80'), 'plan': Decimal('50'), 'response': Decimal('0')}),
            Decimal('70.0'),
        )
        # Chỉ có chất lượng + phản hồi: (40×90 + 10×100) / 50
        self.assertEqual(
            kpi_score({'quality': Decimal('90'), 'on_time': None, 'plan': None, 'response': Decimal('100')}),
            Decimal('92.0'),
        )
        self.assertIsNone(kpi_score({'quality': None}))

    def test_grade_thresholds(self):
        self.assertEqual(grade_for(Decimal('90')), 'A')
        self.assertEqual(grade_for(Decimal('89.9')), 'B')
        self.assertEqual(grade_for(Decimal('75')), 'B')
        self.assertEqual(grade_for(Decimal('74.9')), 'C')
        self.assertEqual(grade_for(None), '')
