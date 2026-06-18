from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from utilities.meal_rules import meal_order_window_for
from utilities.models import MealPushReminderLog, MealPushSubscription
from utilities.push_service import send_meal_reminder_pushes, webpush_configured


@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY='test-public',
    WEBPUSH_VAPID_PRIVATE_KEY='test-private',
    WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@justplay.vn',
    PORTAL_PUBLIC_BASE_URL='https://portal.justplay.vn',
)
class MealPushTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='SX Push',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['utilities'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'utilities': {'view': True, 'edit': True}}},
        )
        self.user = User.objects.create_user(username='sx_push', password='test')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='SX Push',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)
        self.subscription = MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub/1',
            p256dh='p256dh-key',
            auth='auth-key',
        )

    def _meal_window_now(self):
        today = timezone.localdate()
        if today.day in (18, 19):
            today = today.replace(day=10)
        meal_date = today + timedelta(days=1)
        start, _ = meal_order_window_for(meal_date)
        return start + timedelta(minutes=5), meal_date

    def test_webpush_configured(self):
        self.assertTrue(webpush_configured())

    def test_vapid_public_key_endpoint(self):
        resp = self.client.get(reverse('utilities:push_vapid_public_key'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['publicKey'], 'test-public')

    def test_push_subscribe_creates_row(self):
        payload = {
            'endpoint': 'https://push.example/sub/new',
            'keys': {'p256dh': 'abc', 'auth': 'def'},
        }
        resp = self.client.post(
            reverse('utilities:push_subscribe'),
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['created'])
        self.assertTrue(
            MealPushSubscription.objects.filter(endpoint=payload['endpoint'], user=self.user).exists(),
        )

    @patch('utilities.push_service.send_push_to_subscription')
    def test_send_meal_push_reminders(self, mock_send):
        now, meal_date = self._meal_window_now()
        with patch('django.utils.timezone.localtime', return_value=now):
            stats = send_meal_reminder_pushes(now=now)
        self.assertEqual(stats['sent'], 1)
        mock_send.assert_called_once()
        self.assertTrue(
            MealPushReminderLog.objects.filter(employee=self.user, meal_date=meal_date).exists(),
        )

    @patch('utilities.push_service.send_push_to_subscription')
    def test_send_skips_duplicate_log(self, mock_send):
        now, meal_date = self._meal_window_now()
        MealPushReminderLog.objects.create(employee=self.user, meal_date=meal_date)
        with patch('django.utils.timezone.localtime', return_value=now):
            stats = send_meal_reminder_pushes(now=now)
        self.assertEqual(stats['sent'], 0)
        mock_send.assert_not_called()

    def test_push_unsubscribe(self):
        resp = self.client.post(
            reverse('utilities:push_unsubscribe'),
            data={'endpoint': self.subscription.endpoint},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MealPushSubscription.objects.filter(pk=self.subscription.pk).exists())
