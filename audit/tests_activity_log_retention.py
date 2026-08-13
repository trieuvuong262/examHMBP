from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone

from audit.models import UserActivityLog
from audit.retention import (
    ACTIVITY_LOG_RETENTION_DAYS,
    purge_all_old_activity_logs,
    purge_old_activity_logs,
)
from audit.summaries import (
    append_button_to_summary,
    build_detailed_summary,
    get_clicked_button_label,
)
from audit.utils import build_summary
from hrm.models import Profile


def _post_request(path, data=None, *, url_name='', cookies=None):
    factory = RequestFactory()
    request = factory.post(path, data or {})
    request.user = type('U', (), {
        'is_authenticated': True,
        'username': 'tester',
        'get_full_name': lambda s: 'Tester',
    })()
    request.resolver_match = type('M', (), {'url_name': url_name, 'kwargs': {}})()
    if cookies:
        request.COOKIES.update(cookies)
    return request


def _get_request(path, *, url_name='', cookies=None):
    factory = RequestFactory()
    request = factory.get(path)
    request.user = type('U', (), {
        'is_authenticated': True,
        'username': 'tester',
        'get_full_name': lambda s: 'Tester',
    })()
    request.resolver_match = type('M', (), {'url_name': url_name, 'kwargs': {}})()
    if cookies:
        request.COOKIES.update(cookies)
    return request


class ActivityLogRetentionTests(TestCase):
    def _make_log(self, *, days_ago: int, summary='x'):
        log = UserActivityLog.objects.create(
            action=UserActivityLog.ACTION_VIEW,
            summary=summary,
        )
        UserActivityLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago),
        )
        return log

    def test_purge_deletes_older_than_seven_days(self):
        old = self._make_log(days_ago=8, summary='old')
        keep = self._make_log(days_ago=3, summary='keep')
        deleted = purge_all_old_activity_logs(days=ACTIVITY_LOG_RETENTION_DAYS)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(UserActivityLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(UserActivityLog.objects.filter(pk=keep.pk).exists())

    def test_purge_keeps_logs_within_week(self):
        keep = self._make_log(days_ago=6, summary='edge')
        self.assertEqual(purge_old_activity_logs(days=7), 0)
        self.assertTrue(UserActivityLog.objects.filter(pk=keep.pk).exists())

    def test_management_command_dry_run_does_not_delete(self):
        old = self._make_log(days_ago=10, summary='dry')
        out = StringIO()
        call_command('cleanup_activity_logs', '--dry-run', stdout=out)
        self.assertTrue(UserActivityLog.objects.filter(pk=old.pk).exists())
        self.assertIn('dry-run', out.getvalue())

    def test_management_command_deletes_old_logs(self):
        old = self._make_log(days_ago=10, summary='gone')
        call_command('cleanup_activity_logs', stdout=StringIO())
        self.assertFalse(UserActivityLog.objects.filter(pk=old.pk).exists())


class ClickedButtonSummaryTests(TestCase):
    def test_action_field_save_is_recorded(self):
        request = _post_request('/dashboard/users/add/', {
            'full_name': 'Nguyen Van A',
            'username': 'nva',
            'action': 'save',
        }, url_name='user_add')
        self.assertEqual(get_clicked_button_label(request), 'Lưu')
        summary = build_summary(request, UserActivityLog.ACTION_CREATE, 'Nhân sự')
        self.assertIn('nút [Lưu]', summary)

    def test_hidden_clicked_button_field(self):
        request = _post_request('/cong-viec/giao/', {
            'title': 'Viec A',
            'jp_clicked_button': 'Giao việc',
        }, url_name='assign')
        self.assertEqual(get_clicked_button_label(request), 'Giao việc')
        summary = build_detailed_summary(request, UserActivityLog.ACTION_CREATE)
        self.assertIn('nút [Giao việc]', summary)

    def test_cookie_on_get_appends_button(self):
        request = _get_request(
            '/dashboard/users/',
            url_name='user_list',
            cookies={'jp_clicked_btn': 'Thêm mới'},
        )
        summary = build_summary(request, UserActivityLog.ACTION_VIEW, 'Nhân sự')
        self.assertIn('nút [Thêm mới]', summary)
        self.assertIn('danh sách nhân viên', summary)

    def test_humanize_save_bom_action(self):
        request = _post_request('/san-xuat/x/', {'action': 'save_bom'}, url_name='hub')
        self.assertEqual(get_clicked_button_label(request), 'Lưu BOM')

    def test_humanize_bulk_approve_action(self):
        request = _post_request('/san-xuat/x/', {'action': 'bulk_approve'})
        self.assertEqual(get_clicked_button_label(request), 'Duyệt hàng loạt')

    def test_append_skips_when_already_mentioned(self):
        text = 'Tester bấm Đăng xuất khỏi hệ thống'
        self.assertEqual(append_button_to_summary(text, 'Đăng xuất'), text)

    def test_user_add_without_button_still_has_fields(self):
        user = User.objects.create_user(username='hr_btn_test', password='x')
        profile = Profile.objects.get(user=user)
        profile.full_name = 'HR Test'
        profile.save()
        factory = RequestFactory()
        request = factory.post('/dashboard/users/add/', {
            'full_name': 'Nguyen Van A',
            'username': 'nva',
            'employee_code': 'JP001',
        })
        request.user = user
        request.resolver_match = type('M', (), {'url_name': 'user_add', 'kwargs': {}})()
        summary = build_summary(request, UserActivityLog.ACTION_CREATE, 'Nhân sự')
        self.assertIn('tạo nhân viên mới', summary)
        self.assertIn('Nguyen Van A', summary)
