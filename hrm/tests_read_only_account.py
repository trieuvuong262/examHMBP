"""Tài khoản demo chỉ xem — ReadOnlyAccountMiddleware + ẩn khỏi danh sách nhân sự."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.user_search import exclude_hidden_hrm_users, is_read_only_account


class ReadOnlyAccountTests(TestCase):
    def setUp(self):
        self.demo = User.objects.create_user('demo', password='123123sS@@')
        self.demo.profile.must_change_password = False
        self.demo.profile.save()
        self.other = User.objects.create_user('nv_khac', password='x-Strong-123')
        self.client.force_login(self.demo)

    def test_flag(self):
        self.assertTrue(is_read_only_account(self.demo))
        self.assertFalse(is_read_only_account(self.other))

    def test_hidden_from_hrm_list_queryset(self):
        names = set(exclude_hidden_hrm_users(User.objects.all()).values_list('username', flat=True))
        self.assertNotIn('demo', names)
        self.assertIn('nv_khac', names)

    def test_post_is_blocked(self):
        resp = self.client.post(reverse('password_change'), {
            'old_password': '123123sS@@',
            'new_password1': 'NewPass-9876!',
            'new_password2': 'NewPass-9876!',
        })
        self.assertIn(resp.status_code, (302, 403))
        self.demo.refresh_from_db()
        self.assertTrue(self.demo.check_password('123123sS@@'))

    def test_ajax_post_returns_json_403(self):
        resp = self.client.post('/', {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['status'], 'error')

    def test_blocked_get_urls(self):
        for url in (
            reverse('password_change'),
            reverse('user_export_excel'),
            reverse('user_list'),
            '/admin-panel/',
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                # 403 (read-only) hoặc 302 (middleware phân quyền module chặn trước).
                self.assertIn(resp.status_code, (302, 403), url)
                self.assertNotIn('attachment', resp.get('Content-Disposition', ''))

    def test_middleware_blocks_hrm_list_even_with_module_access(self):
        from django.test import RequestFactory

        from PortalJustPlay.middleware import ReadOnlyAccountMiddleware

        mw = ReadOnlyAccountMiddleware(lambda r: None)
        rf = RequestFactory()
        for url in (reverse('user_list'), reverse('user_export_excel'), '/san-xuat/x/print/'):
            req = rf.get(url)
            req.user = self.demo
            self.assertTrue(mw._is_blocked(req, url), url)
        req = rf.get(reverse('home_portal'))
        req.user = self.demo
        self.assertFalse(mw._is_blocked(req, reverse('home_portal')))

    def test_view_page_gets_print_block_style(self):
        resp = self.client.get(reverse('home_portal'), follow=True)
        self.assertNotEqual(resp.status_code, 403)
        if resp.status_code == 200 and b'</head>' in resp.content:
            self.assertIn(b'readonly-no-print', resp.content)

    def test_logout_allowed(self):
        resp = self.client.post('/accounts/logout/')
        self.assertNotEqual(resp.status_code, 403)

    def test_other_user_not_affected(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse('password_change'))
        self.assertNotEqual(resp.status_code, 403)

    def test_password_reset_cannot_resolve_demo(self):
        from zalo.password_reset import resolve_user_for_password_reset

        self.assertIsNone(resolve_user_for_password_reset('demo'))
        self.assertEqual(resolve_user_for_password_reset('nv_khac'), self.other)


class ReadOnlyAccountNotApproverTests(TestCase):
    """demo là Trưởng phòng (xem) nhưng không được thành người duyệt / thêm bước duyệt."""

    def test_demo_department_head_is_not_manager(self):
        from hrm.concurrent_positions import (
            department_has_department_heads_extended,
            find_manager_with_subordinate,
        )
        from hrm.models import Department
        from hrm.permissions import ROLE_DEPARTMENT_HEAD

        dept = Department.objects.create(name='IT test RO', sort_order=99)
        demo = User.objects.create_user('demo', password='123123sS@@')
        demo.profile.department = dept
        demo.profile.role = ROLE_DEPARTMENT_HEAD
        demo.profile.job_position = 'Trưởng phòng'
        demo.profile.is_employed = True
        demo.profile.save()
        staff = User.objects.create_user('it_nv_ro', password='x-Strong-123')
        staff.profile.department = dept
        staff.profile.is_employed = True
        staff.profile.save()

        self.assertFalse(department_has_department_heads_extended(dept))
        self.assertIsNone(find_manager_with_subordinate(staff, ROLE_DEPARTMENT_HEAD))
