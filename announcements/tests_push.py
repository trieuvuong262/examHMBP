from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from announcements.models import Announcement, AnnouncementRead
from announcements.push_service import announcement_push_payload, send_announcement_push
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from utilities.models import MealPushSubscription


@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY='test-public',
    WEBPUSH_VAPID_PRIVATE_KEY='test-private',
    WEBPUSH_VAPID_CLAIMS_EMAIL='mailto:test@justplay.vn',
    PORTAL_PUBLIC_BASE_URL='https://portal.justplay.vn',
)
class AnnouncementPushTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='VP Ann', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['announcements'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'announcements': {'view': True}}},
        )
        self.user = User.objects.create_user(username='ann_push', password='x')
        Profile.objects.filter(user=self.user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Ann Push',
            is_employed=True,
        )
        self.subscription = MealPushSubscription.objects.create(
            user=self.user,
            endpoint='https://push.example/sub/ann',
            p256dh='p256dh',
            auth='auth',
        )
        self.announcement = Announcement.objects.create(
            title='Thông báo test',
            summary='Nội dung tóm tắt',
            is_active=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_payload_contains_title_and_url(self):
        payload = announcement_push_payload(self.announcement)
        self.assertIn('Thông báo test', payload)
        self.assertIn(f'/announcements/{self.announcement.pk}/', payload)

    @patch('announcements.push_service.send_push_to_subscription')
    def test_send_announcement_push(self, mock_send):
        stats = send_announcement_push(self.announcement)
        self.assertEqual(stats['sent'], 1)
        mock_send.assert_called_once()

    def test_poll_unread(self):
        resp = self.client.get(reverse('announcements:push_poll'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['has_new'])
        self.assertEqual(data['announcement_id'], self.announcement.pk)

    def test_poll_no_unread_after_ack(self):
        AnnouncementRead.objects.create(announcement=self.announcement, user=self.user)
        resp = self.client.get(reverse('announcements:push_poll'))
        self.assertFalse(resp.json()['has_new'])
