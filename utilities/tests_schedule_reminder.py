from datetime import date, time, timedelta
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

        with patch('utilities.schedule_push_service.send_push_to_subscription') as mock_push:
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

        with patch('utilities.schedule_push_service.send_push_to_subscription'):
            stats = send_schedule_reminder_pushes(now=fire_at)
        self.assertEqual(stats['sent'], 1)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_home_create_weekly_via_post(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('home_portal'),
            {
                'form_id': 'schedule_reminder',
                'title': 'Gọi khách',
                'body': 'Nhắc gọi lại ABC',
                'repeat_mode': ScheduleReminder.REPEAT_WEEKLY,
                'weekdays': ['1', '3', '5'],
                'remind_time': '09:30',
            },
        )
        self.assertRedirects(resp, f'{reverse("home_portal")}#nhac-lich', fetch_redirect_response=False)
        reminder = ScheduleReminder.objects.get(user=self.user, title='Gọi khách')
        self.assertEqual(reminder.weekday_list(), [1, 3, 5])
        self.assertEqual(reminder.remind_time, time(9, 30))

    def test_home_create_once_via_post(self):
        self.client.force_login(self.user)
        once = timezone.localdate() + timedelta(days=3)
        resp = self.client.post(
            reverse('home_portal'),
            {
                'form_id': 'schedule_reminder',
                'title': 'Deadline',
                'body': '',
                'repeat_mode': ScheduleReminder.REPEAT_ONCE,
                'once_date': once.isoformat(),
                'remind_time': '14:00',
            },
        )
        self.assertRedirects(resp, f'{reverse("home_portal")}#nhac-lich', fetch_redirect_response=False)
        reminder = ScheduleReminder.objects.get(user=self.user, title='Deadline')
        self.assertEqual(reminder.once_date, once)
        self.assertEqual(reminder.repeat_mode, ScheduleReminder.REPEAT_ONCE)

    def test_delete_reminder(self):
        reminder = ScheduleReminder.objects.create(
            user=self.user,
            title='Xóa tôi',
            repeat_mode=ScheduleReminder.REPEAT_WEEKLY,
            weekdays=[1],
            remind_time=time(8, 0),
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse('schedule_reminder_delete', args=[reminder.pk]))
        self.assertRedirects(resp, f'{reverse("home_portal")}#nhac-lich')
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_old_utilities_url_redirects_home(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('utilities:schedule_reminder_home'))
        self.assertRedirects(resp, f'{reverse("home_portal")}#nhac-lich')
