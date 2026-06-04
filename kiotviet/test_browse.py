from django.test import RequestFactory, TestCase

from kiotviet.browse import api_current_item, fetch_api_page, get_page_number, paginate_api_meta


class KiotVietBrowseHelpersTests(TestCase):
    def test_get_page_number_defaults(self):
        request = RequestFactory().get('/')
        self.assertEqual(get_page_number(request), 1)
        request = RequestFactory().get('/', {'page': '3'})
        self.assertEqual(get_page_number(request), 3)

    def test_api_current_item(self):
        self.assertEqual(api_current_item(1), 0)
        self.assertEqual(api_current_item(2), 30)

    def test_paginate_api_meta(self):
        request = RequestFactory().get('/', {'q': 'x', 'page': '2'})
        page_obj, qs = paginate_api_meta(request, 75)
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.num_pages, 3)
        self.assertEqual(qs, 'q=x')

    def test_fetch_api_page(self):
        def fake_list(**params):
            self.assertEqual(params['pageSize'], 30)
            self.assertEqual(params['currentItem'], 30)
            return {'total': 50, 'data': [{'id': 1}]}

        rows, total = fetch_api_page(fake_list, {'orderBy': 'name'}, 2)
        self.assertEqual(total, 50)
        self.assertEqual(len(rows), 1)
