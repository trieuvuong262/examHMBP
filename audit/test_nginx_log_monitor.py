from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from audit.services.nginx_log_monitor import (
    clamp_hours,
    collect_nginx_log_watch,
    parse_access_line,
    summarize_access_lines,
)
from audit.services.vps_monitor import _demux_docker_logs
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_AUDIT
from hrm.permissions import ROLE_DIRECTOR


SAMPLE = """
203.0.113.9 - - [15/Sep/2026:02:39:34 +0000] "GET /.env HTTP/1.1" 403 169 "-" "Mozilla/5.0"
203.0.113.9 - - [15/Sep/2026:02:39:35 +0000] "GET /wp-admin/ HTTP/1.1" 403 169 "-" "curl/8.0"
14.161.25.119 - - [15/Sep/2026:02:40:01 +0000] "POST /accounts/login/ HTTP/2.0" 200 1200 "https://portal.justplay.vn/accounts/login/" "Mozilla/5.0"
14.161.25.119 - - [15/Sep/2026:02:40:02 +0000] "GET /reports/sx/today/ HTTP/2.0" 200 8000 "-" "Mozilla/5.0"
10.0.0.8 - - [15/Sep/2026:02:41:00 +0000] "GET /favicon.ico HTTP/1.1" 404 120 "-" "Mozilla/5.0"
10.0.0.8 - - [15/Sep/2026:02:41:11 +0000] "GET /sw.js HTTP/1.1" 502 32 "-" "Mozilla/5.0"
"""


class NginxLogParseTests(SimpleTestCase):
    def test_clamp_hours(self):
        self.assertEqual(clamp_hours(24), 24)
        self.assertEqual(clamp_hours('6'), 6)
        self.assertEqual(clamp_hours('99'), 24)
        self.assertEqual(clamp_hours('nope'), 24)

    def test_parse_scanner_and_login(self):
        lines = SAMPLE.strip().splitlines()
        env = parse_access_line(lines[0])
        self.assertEqual(env['status'], 403)
        self.assertTrue(env['scanner'])
        self.assertEqual(env['path'], '/.env')

        login = parse_access_line(lines[2])
        self.assertTrue(login['login_post'])
        self.assertFalse(login['scanner'])

        favicon = parse_access_line(lines[4])
        self.assertTrue(favicon['noise'])

    def test_parse_docker_timestamp_prefix(self):
        line = (
            '2026-09-15T02:39:34.000000000Z 1.2.3.4 - - [15/Sep/2026:02:39:34 +0000] '
            '"GET /.git/config HTTP/1.1" 403 12 "-" "curl/8"'
        )
        row = parse_access_line(line)
        self.assertEqual(row['ip'], '1.2.3.4')
        self.assertTrue(row['scanner'])

    def test_summarize_counts(self):
        summary = summarize_access_lines(SAMPLE, hours=24)
        self.assertEqual(summary['count_scanner'], 2)
        self.assertEqual(summary['count_login_post'], 1)
        self.assertEqual(summary['count_5xx'], 1)
        self.assertGreaterEqual(summary['count_4xx'], 2)
        paths = [item[0] for item in summary['top_paths']]
        self.assertTrue(any('/.env' in p for p in paths))
        self.assertFalse(any('favicon' in p for p in paths))
        self.assertTrue(any('login' in p for p in paths))

    def test_demux_docker_logs(self):
        self.assertEqual(_demux_docker_logs(b'hello\n'), 'hello\n')
        frame = bytes([1, 0, 0, 0, 0, 0, 0, 5]) + b'abcde'
        self.assertEqual(_demux_docker_logs(frame), 'abcde')


class NginxLogWatchUnavailableTests(SimpleTestCase):
    @patch('audit.services.nginx_log_monitor.docker_available', return_value=False)
    def test_collect_without_docker(self, _mock):
        watch = collect_nginx_log_watch(hours=24)
        self.assertFalse(watch['available'])
        self.assertIn('Docker', watch['error'])


class NginxLogPageTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT Nginx Watch', sort_order=91)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['audit'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True, 'edit': True, 'export': True}}},
        )
        self.user = User.objects.create_user(username='it_admin_nginx', password='adminpass123')
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.department = self.dept
        profile.role = ROLE_DIRECTOR
        profile.save()
        self.client.force_login(self.user)

    def test_nginx_tab_renders_summary(self):
        fake = {
            'hours': 24,
            'available': True,
            'container': 'portaljustplay-nginx-1',
            'error': None,
            'line_count': 10,
            'skipped_lines': 0,
            'count_4xx': 3,
            'count_5xx': 1,
            'count_scanner': 2,
            'count_login_post': 1,
            'top_paths': [('403 GET /.env', 2)],
            'top_ips': [('203.0.113.9', 2)],
            'recent': [{
                'ip': '203.0.113.9',
                'time': '15/Sep/2026:02:39:34 +0000',
                'method': 'GET',
                'path': '/.env',
                'status': 403,
                'ua': 'curl/8',
                'scanner': True,
                'login_post': False,
            }],
        }
        with patch(
            'audit.services.nginx_log_monitor.collect_nginx_log_watch',
            return_value=fake,
        ):
            response = self.client.get(reverse('audit:login_security'), {'tab': 'nginx'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nginx log')
        self.assertContains(response, 'portaljustplay-nginx-1')
        self.assertContains(response, '/.env')
        self.assertContains(response, 'scanner')
