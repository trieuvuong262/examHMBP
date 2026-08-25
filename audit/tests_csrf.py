import json
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from PortalJustPlay.csrf import csrf_failure


def _request(path='/accounts/login/', *, ajax=False, ua=''):
    extra = {}
    if ajax:
        extra['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
    if ua:
        extra['HTTP_USER_AGENT'] = ua
    request = RequestFactory().post(path, {'username': 'x', 'password': 'y'}, **extra)
    request.user = AnonymousUser()
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


class CsrfFailureViewTests(TestCase):
    def test_html_page_guides_user_to_login(self):
        resp = csrf_failure(_request(), reason='CSRF token missing.')
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, 'Phiên làm việc không hợp lệ', status_code=403)
        self.assertContains(resp, 'Đăng nhập lại', status_code=403)
        self.assertContains(resp, 'đóng hẳn', status_code=403)
        self.assertNotContains(resp, 'DEBUG=True', status_code=403)
        self.assertNotContains(resp, 'Bị cấm (403)', status_code=403)

    def test_ajax_returns_json(self):
        resp = csrf_failure(_request(ajax=True))
        self.assertEqual(resp.status_code, 403)
        data = json.loads(resp.content)
        self.assertEqual(data.get('status'), 'error')
        self.assertTrue(data.get('csrf'))
        self.assertEqual(data.get('login_url'), reverse('login'))

    def test_zalo_ua_shows_open_browser_page(self):
        resp = csrf_failure(
            _request(ua='Mozilla/5.0 (Linux; Android 14) Mobile Zalo android / 250'),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, 'Không mở được trong Zalo', status_code=403)
        self.assertNotContains(resp, 'Bị cấm (403)', status_code=403)
