from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile
from kiotviet.client import KiotVietAPIError, KiotVietClient


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='test-id',
    KIOTVIET_CLIENT_SECRET='test-secret',
)
class KiotVietClientTests(TestCase):
    def test_is_configured(self):
        self.assertTrue(KiotVietClient.is_configured())

    @patch('kiotviet.client.requests.post')
    @patch('kiotviet.client.requests.request')
    def test_list_customers(self, mock_request, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'access_token': 'tok', 'expires_in': 3600},
        )
        mock_request.return_value = MagicMock(
            status_code=200,
            content=b'{"total":1,"data":[{"id":1,"code":"KH01","name":"A"}]}',
            json=lambda: {'total': 1, 'data': [{'id': 1, 'code': 'KH01', 'name': 'A'}]},
        )
        client = KiotVietClient()
        payload = client.list_customers(name='A')
        self.assertEqual(payload['total'], 1)
        mock_request.assert_called_once()


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='test-id',
    KIOTVIET_CLIENT_SECRET='test-secret',
)
class KiotVietViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KD KiotViet Test')
        self.user = User.objects.create_user(username='kvuser', password='pass12345')
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.full_name = 'KV User'
        profile.department = self.dept
        profile.role = 'EMPLOYEE'
        profile.save()
        self.http = Client()
        self.http.login(username='kvuser', password='pass12345')

    def test_lookup_page_requires_login(self):
        anon = Client()
        response = anon.get(reverse('kiotviet:customer_lookup'))
        self.assertEqual(response.status_code, 302)

    def test_order_lookup_url(self):
        response = self.http.get(reverse('kiotviet:order_lookup'))
        self.assertEqual(response.status_code, 200)

    def test_invoice_lookup_url(self):
        response = self.http.get(reverse('kiotviet:invoice_lookup'))
        self.assertEqual(response.status_code, 200)

    def test_product_lookup_url(self):
        response = self.http.get(reverse('kiotviet:product_lookup'))
        self.assertEqual(response.status_code, 200)

    def test_stock_lookup_url(self):
        response = self.http.get(reverse('kiotviet:stock_lookup'))
        self.assertEqual(response.status_code, 200)

    def test_purchase_lookup_url(self):
        response = self.http.get(reverse('kiotviet:purchase_lookup'))
        self.assertEqual(response.status_code, 200)

    @patch('kiotviet.views.KiotVietClient.list_customers')
    def test_customer_browse_shows_first_page(self, mock_list):
        mock_list.return_value = {
            'total': 45,
            'data': [
                {'id': i, 'code': f'KH{i:02d}', 'name': f'Khách {i}'}
                for i in range(1, 31)
            ],
        }
        response = self.http.get(reverse('kiotviet:customer_lookup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'KH01')
        self.assertContains(response, 'Trang 1/')
        mock_list.assert_called_once()
        kwargs = mock_list.call_args.kwargs
        self.assertEqual(kwargs['pageSize'], 30)
        self.assertEqual(kwargs['currentItem'], 0)

    @patch('kiotviet.views.KiotVietClient.list_customers')
    def test_customer_browse_page_two(self, mock_list):
        mock_list.return_value = {'total': 45, 'data': [{'id': 31, 'code': 'KH31', 'name': 'Khách 31'}]}
        response = self.http.get(reverse('kiotviet:customer_lookup'), {'page': '2'})
        self.assertEqual(response.status_code, 200)
        kwargs = mock_list.call_args.kwargs
        self.assertEqual(kwargs['currentItem'], 30)

    @patch('kiotviet.views.KiotVietClient.get_customer_by_code')
    @patch('kiotviet.views.KiotVietClient.list_customers')
    def test_lookup_search_by_name(self, mock_list, mock_by_code):
        mock_list.return_value = {
            'total': 1,
            'data': [
                {
                    'id': 99,
                    'code': 'KH99',
                    'name': 'Nguyen Van A',
                    'contactNumber': '0901234567',
                },
            ],
        }
        response = self.http.get(
            reverse('kiotviet:customer_lookup'),
            {'type': 'name', 'q': 'Nguyen'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nguyen Van A')
        self.assertContains(response, 'KH99')
        mock_list.assert_called_once()
        mock_by_code.assert_not_called()

    @patch('kiotviet.views.KiotVietClient.get_customer')
    def test_customer_detail(self, mock_get):
        mock_get.return_value = {
            'id': 99,
            'code': 'KH99',
            'name': 'Nguyen Van A',
            'contactNumber': '0901234567',
            'email': 'a@example.com',
        }
        response = self.http.get(reverse('kiotviet:customer_detail', kwargs={'customer_id': 99}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nguyen Van A')

    @override_settings(KIOTVIET_ENABLED=False)
    def test_disabled_redirects_home(self):
        response = self.http.get(reverse('kiotviet:customer_lookup'))
        self.assertRedirects(response, reverse('home_portal'))

    def test_staff_without_kiotviet_module_denied(self):
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['reports'],
        )
        staff = User.objects.create_user(
            username='staff_no_kv',
            password='pass12345',
            is_staff=True,
        )
        profile, _ = Profile.objects.get_or_create(user=staff)
        profile.department = self.dept
        profile.role = 'EMPLOYEE'
        profile.save()
        client = Client()
        client.login(username='staff_no_kv', password='pass12345')
        response = client.get(reverse('kiotviet:customer_lookup'))
        self.assertRedirects(response, reverse('home_portal'))
