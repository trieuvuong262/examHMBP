from django.test import SimpleTestCase

from audit.services.nginx_log_monitor import parse_access_line, summarize_access_lines


SAMPLE = """
192.168.30.58 - - [18/Sep/2026:08:41:06 +0000] "GET /tien-ich/push/schedule-poll/ HTTP/2.0" 502 123 "-" "Mozilla/5.0"
123.20.61.39 - - [18/Sep/2026:08:41:00 +0000] "GET /announcements/push/poll/ HTTP/2.0" 504 123 "-" "Mozilla/5.0"
192.168.10.249 - - [18/Sep/2026:08:41:03 +0000] "GET /nhat-ky/rustdesk/trang-thai/ HTTP/2.0" 502 123 "-" "Mozilla/5.0"
192.168.10.252 - - [18/Sep/2026:08:40:53 +0000] "GET /sw.js HTTP/2.0" 502 123 "-" "Mozilla/5.0"
192.168.10.250 - - [18/Sep/2026:07:25:33 +0000] "GET /kho-npl/phieu-huy/ HTTP/2.0" 500 3235 "https://portal.justplay.vn/" "Mozilla/5.0"
94.154.43.203 - - [18/Sep/2026:08:41:07 +0000] "PROPFIND / HTTP/1.1" 503 112 "-" "-"
102.220.161.102 - - [18/Sep/2026:08:10:00 +0000] "GET /.git/config HTTP/1.1" 404 12 "-" "Mozilla/5.0"
102.220.161.102 - - [18/Sep/2026:08:10:01 +0000] "POST /cgi-bin/../../../../../../../../../../bin/sh HTTP/1.1" 400 12 "-" "-"
94.154.43.203 - - [18/Sep/2026:08:41:09 +0000] "GET /index.php HTTP/1.1" 503 112 "-" "Mozilla/5.0"
1.1.1.1 - - [18/Sep/2026:08:00:00 +0000] "GET /favicon.ico HTTP/1.1" 404 12 "-" "Mozilla/5.0"
1.1.1.1 - - [18/Sep/2026:08:00:01 +0000] "GET /accounts/login/ HTTP/2.0" 200 800 "-" "Mozilla/5.0"
"""


class NginxLogMonitorTests(SimpleTestCase):
    def test_classifies_background_poll(self):
        row = parse_access_line(
            '192.168.30.58 - - [18/Sep/2026:08:41:06 +0000] '
            '"GET /tien-ich/push/schedule-poll/ HTTP/2.0" 502 123 "-" "Mozilla/5.0"',
        )
        self.assertTrue(row['background'])
        self.assertFalse(row['scanner'])

    def test_classifies_scanner_git_and_php_and_propfind(self):
        git = parse_access_line(
            '1.2.3.4 - - [18/Sep/2026:08:10:00 +0000] '
            '"GET /.git/config HTTP/1.1" 404 12 "-" "curl"',
        )
        php = parse_access_line(
            '1.2.3.4 - - [18/Sep/2026:08:10:00 +0000] '
            '"GET /index.php HTTP/1.1" 444 0 "-" "curl"',
        )
        propfind = parse_access_line(
            '1.2.3.4 - - [18/Sep/2026:08:10:00 +0000] '
            '"PROPFIND / HTTP/1.1" 444 0 "-" "-"',
        )
        self.assertTrue(git['scanner'])
        self.assertTrue(php['scanner'])
        self.assertTrue(propfind['scanner'])

    def test_top_paths_hides_background_keeps_real_500_and_scanner(self):
        summary = summarize_access_lines(SAMPLE, hours=24)
        paths = [item[0] for item in summary['top_paths']]
        self.assertTrue(any('phieu-huy' in path for path in paths))
        self.assertTrue(
            any(
                '.git/config' in path or 'cgi-bin' in path or 'index.php' in path
                for path in paths
            ),
        )
        self.assertFalse(any('schedule-poll' in path for path in paths))
        self.assertFalse(any('push/poll' in path for path in paths))
        self.assertFalse(any('rustdesk' in path for path in paths))
        self.assertGreater(summary['count_5xx_background'], 0)
        self.assertGreater(summary['count_scanner'], 0)
        self.assertEqual(summary['count_5xx'], 7)
