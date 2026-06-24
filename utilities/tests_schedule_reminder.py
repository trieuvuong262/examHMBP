from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from utilities.models import MealPushSubscription, ScheduleReminder, ScheduleReminderPushLog
from utilities.schedule_push_service import send_schedule_reminder_pushes


class ScheduleReminderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sched_user', password='test')
        self.client = Client(HTTP_HOST='testserver')

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_weekly_reminder_sends_push(self):
        now = timezone.localtime(timezone.now())
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Họp team',
            body='Chuẩn bị báo cáo tuần',
            repeat_mode=ScheduleReminder.REPEAT_WEEKLY,
            weekdays=[now.isoweekday()],
            remind_time=now.time().replace(second=0, microsecond=0),
        )
        MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub/1',
            p256dh='key',
            auth='auth',
        )

        with patch('utilities.push_service.send_push_to_subscription') as mock_push:
            stats = send_schedule_reminder_pushes(now=now)
        self.assertEqual(stats['sent'], 1)
        mock_push.assert_called_once()
        self.assertTrue(
            ScheduleReminderPushLog.objects.filter(reminder=reminder, fire_date=now.date()).exists(),
        )
        reminder.refresh_from_db()
        self.assertTrue(reminder.is_active)

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_once_reminder_deactivates_after_push(self):
        today = timezone.localdate()
        remind_time = (timezone.localtime() + timedelta(hours=1)).time().replace(second=0, microsecond=0)
        fire_at = timezone.make_aware(
            timezone.datetime.combine(today, remind_time),
            timezone.get_current_timezone(),
        )
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Một lần',
            repeat_mode=ScheduleReminder.REPEAT_ONCE,
            once_date=today,
            weekdays=[today.isoweekday()],
            remind_time=remind_time,
        )
        MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub/2',
            p256dh='key',
            auth='auth',
        )

        with patch('utilities.push_service.send_push_to_subscription'):
            stats = send_schedule_reminder_pushes(now=fire_at)
        self.assertEqual(stats['sent'], 1)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_create_weekly_via_tools_page(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('tools:schedule_reminder'),
            {
                'title': 'Gọi khách',
                'body': 'Nhắc gọi lại ABC',
                'repeat_mode': ScheduleReminder.REPEAT_WEEKLY,
                'weekdays': ['1', '3', '5'],
                'remind_time': '09:30',
            },
        )
        self.assertRedirects(resp, reverse('tools:schedule_reminder'))
        reminder = ScheduleReminder.objects.get(user=self.user, title='Gọi khách')
        self.assertEqual(reminder.weekday_list(), [1, 3, 5])
        self.assertEqual(reminder.remind_time, time(9, 30))

    def test_create_once_via_tools_page(self):
        self.client.force_login(self.user)
        once = timezone.localdate() + timedelta(days=3)
        resp = self.client.post(
            reverse('tools:schedule_reminder'),
            {
                'title': 'Deadline',
                'body': '',
                'repeat_mode': ScheduleReminder.REPEAT_ONCE,
                'once_date': once.isoformat(),
                'remind_time': '14:00',
            },
        )
        self.assertRedirects(resp, reverse('tools:schedule_reminder'))
        reminder = ScheduleReminder.objects.get(user=self.user, title='Deadline')
        self.assertEqual(reminder.once_date, once)

    def test_delete_reminder(self):
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Xóa tôi',
            repeat_mode=ScheduleReminder.REPEAT_WEEKLY,
            weekdays=[1],
            remind_time=time(8, 0),
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse('tools:schedule_reminder_delete', args=[reminder.pk]))
        self.assertRedirects(resp, reverse('tools:schedule_reminder'))
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_old_utilities_url_redirects_tools(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('utilities:schedule_reminder_home'))
        self.assertRedirects(resp, reverse('tools:schedule_reminder'))

    def test_home_shows_schedule_tool_tile(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('home_portal'))
        self.assertContains(resp, 'Nhắc lịch')
        self.assertContains(resp, reverse('tools:schedule_reminder'))

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_schedule_push_poll(self):
        now = timezone.localtime(timezone.now())
        ScheduleReminder.objects.create(
            user=self.user,
            title='Poll nhắc',
            repeat_mode=ScheduleReminder.REPEAT_WEEKLY,
            weekdays=[now.isoweekday()],
            remind_time=now.time().replace(second=0, microsecond=0),
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse('utilities:schedule_push_poll'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['has_due'])
        self.assertEqual(data['title'], 'Poll nhắc')

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_grace_window_fires_after_minute(self):
        from utilities.schedule_reminder_logic import should_fire_reminder

        now = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        remind_time = (now - timedelta(minutes=1)).time()
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Grace',
            repeat_mode=ScheduleReminder.REPEAT_WEEKLY,
            weekdays=[now.isoweekday()],
            remind_time=remind_time,
        )
        MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub-grace',
            p256dh='key',
            auth='auth',
        )
        self.assertTrue(should_fire_reminder(reminder, now))
        with patch('utilities.push_service.send_push_to_subscription') as mock_push:
            stats = send_schedule_reminder_pushes(now=now)
        self.assertEqual(stats['sent'], 1, stats)
        mock_push.assert_called()

    @override_settings(
        WEBPUSH_VAPID_PUBLIC_KEY='test-public',
        WEBPUSH_VAPID_PRIVATE_KEY='test-private',
        WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@example.com',
    )
    def test_schedule_test_push_endpoint(self):
        MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub-test',
            p256dh='key',
            auth='auth',
        )
        self.client.force_login(self.user)
        with patch('utilities.push_service.send_test_schedule_push', return_value={'sent': 1}):
            resp = self.client.post(reverse('utilities:push_test_schedule'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
