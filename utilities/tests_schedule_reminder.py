from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from utilities.models import MealPushSubscription, ScheduleReminder
from utilities.schedule_push_service import send_schedule_reminder_pushes


class ScheduleReminderTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Sched Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['utilities'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'utilities': {
                        'view': True,
                        'edit': True,
                        'menus': {
                            'schedule_reminder': {
                                'view': True,
                                'create': True,
                                'update': True,
                                'delete': True,
                            },
                        },
                    },
                },
            },
        )
        self.user = User.objects.create_user(username='sched_user', password='test')
        Profile.objects.filter(user=self.user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='sched_user',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_create_reminder_and_send_push(self):
        remind_at = timezone.now() + timedelta(minutes=30)
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Họp team',
            body='Chuẩn bị báo cáo tuần',
            remind_at=remind_at,
        )
        MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub/1',
            p256dh='key',
            auth='auth',
        )

        due = remind_at + timedelta(seconds=5)
        with patch('utilities.schedule_push_service.send_push_to_subscription') as mock_push:
            stats = send_schedule_reminder_pushes(now=due)
        self.assertEqual(stats['sent'], 1)
        mock_push.assert_called_once()
        payload = mock_push.call_args[0][1]
        self.assertIn('Họp team', payload)
        self.assertIn('Chuẩn bị báo cáo tuần', payload)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.push_sent_at)

    def test_home_create_via_post(self):
        self.client.force_login(self.user)
        remind_at = timezone.now() + timedelta(hours=2)
        local_value = timezone.localtime(remind_at).strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(
            reverse('utilities:schedule_reminder_home'),
            {
                'title': 'Gọi khách',
                'body': 'Nhắc gọi lại ABC',
                'remind_at': local_value,
            },
        )
        self.assertRedirects(resp, reverse('utilities:schedule_reminder_home'))
        self.assertTrue(
            ScheduleReminder.objects.filter(user=self.user, title='Gọi khách').exists(),
        )

    def test_delete_reminder(self):
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Xóa tôi',
            remind_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse('utilities:schedule_reminder_delete', args=[reminder.pk]))
        self.assertRedirects(resp, reverse('utilities:schedule_reminder_home'))
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)
