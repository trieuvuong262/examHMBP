from django.test import RequestFactory, SimpleTestCase

from san_xuat.list_filter_persist import (
    SX_LIST_QS_SESSION_KEY,
    came_from_other_sx_page,
    is_sx_filter_list_path,
    maybe_redirect_sx_list_filters,
    persistable_query,
)


class _Session(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modified = False


def _with_session(request, data=None):
    request.session = _Session(data or {})
    return request


class SxListFilterPersistTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_list_vs_detail_paths(self):
        self.assertTrue(is_sx_filter_list_path('/san-xuat/dieu-phoi/lenh-sx/'))
        self.assertTrue(is_sx_filter_list_path('/san-xuat/don-hang/'))
        self.assertTrue(is_sx_filter_list_path('/san-xuat/ho-so/'))
        self.assertTrue(is_sx_filter_list_path('/san-xuat/cong-viec-to/cat/'))
        self.assertTrue(is_sx_filter_list_path('/kho-npl/danh-muc/'))
        self.assertFalse(is_sx_filter_list_path('/kho-npl/danh-muc/4181/'))
        self.assertFalse(is_sx_filter_list_path('/kho-npl/danh-muc/them/'))
        self.assertFalse(is_sx_filter_list_path('/san-xuat/dieu-phoi/lenh-sx/12/'))
        self.assertFalse(is_sx_filter_list_path('/san-xuat/dieu-phoi/lenh-sx/them/'))
        self.assertFalse(is_sx_filter_list_path('/san-xuat/api/tim-ma-sp/'))
        self.assertFalse(is_sx_filter_list_path('/san-xuat/xuat-excel/dispatch_mo/'))
        self.assertFalse(is_sx_filter_list_path('/bao-cao/'))

    def test_persistable_query_drops_reset_and_blanks(self):
        request = self.factory.get(
            '/san-xuat/dieu-phoi/lenh-sx/',
            {'code': 'LSX-1', 'name': '', 'sx_reset': '1', 'export': 'csv'},
        )
        self.assertEqual(persistable_query(request), 'code=LSX-1')

    def test_came_from_detail_not_same_list(self):
        request = self.factory.get('/san-xuat/dieu-phoi/lenh-sx/')
        request.META['HTTP_HOST'] = 'testserver'
        request.META['HTTP_REFERER'] = 'http://testserver/san-xuat/dieu-phoi/lenh-sx/9/'
        self.assertTrue(came_from_other_sx_page(request))

        request.META['HTTP_REFERER'] = 'http://testserver/san-xuat/dieu-phoi/lenh-sx/?code=X'
        self.assertFalse(came_from_other_sx_page(request))

        request.META['HTTP_REFERER'] = 'http://testserver/'
        self.assertFalse(came_from_other_sx_page(request))

    def test_saves_query_and_restores_after_back_from_detail(self):
        list_path = '/san-xuat/dieu-phoi/lenh-sx/'
        filtered = _with_session(
            self.factory.get(list_path, {'code': 'LSX-1', 'date_from': '2026-09-01'}),
        )
        self.assertIsNone(maybe_redirect_sx_list_filters(filtered))
        saved = filtered.session[SX_LIST_QS_SESSION_KEY][list_path]
        self.assertIn('code=LSX-1', saved)

        back = _with_session(
            self.factory.get(list_path),
            {SX_LIST_QS_SESSION_KEY: dict(filtered.session[SX_LIST_QS_SESSION_KEY])},
        )
        back.META['HTTP_HOST'] = 'testserver'
        back.META['HTTP_REFERER'] = 'http://testserver/san-xuat/dieu-phoi/lenh-sx/9/'
        response = maybe_redirect_sx_list_filters(back)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)
        self.assertIn('code=LSX-1', response['Location'])
        self.assertIn('date_from=2026-09-01', response['Location'])

    def test_clear_from_same_list_forgets_saved_query(self):
        list_path = '/san-xuat/dieu-phoi/lenh-sx/'
        request = _with_session(
            self.factory.get(list_path),
            {SX_LIST_QS_SESSION_KEY: {list_path: 'code=LSX-1'}},
        )
        request.META['HTTP_HOST'] = 'testserver'
        request.META['HTTP_REFERER'] = 'http://testserver/san-xuat/dieu-phoi/lenh-sx/?code=LSX-1'
        self.assertIsNone(maybe_redirect_sx_list_filters(request))
        self.assertNotIn(list_path, request.session.get(SX_LIST_QS_SESSION_KEY) or {})

    def test_sx_reset_strips_param_and_keeps_other_keys(self):
        list_path = '/san-xuat/bao-cao-van-hanh/'
        request = _with_session(
            self.factory.get(list_path, {'sx_reset': '1', 'tab': 'theo-ngay'}),
        )
        response = maybe_redirect_sx_list_filters(request)
        self.assertIsNotNone(response)
        self.assertEqual(response['Location'], f'{list_path}?tab=theo-ngay')
        self.assertEqual(request.session[SX_LIST_QS_SESSION_KEY][list_path], 'tab=theo-ngay')

    def test_skips_ajax_and_non_list(self):
        ajax = _with_session(
            self.factory.get('/san-xuat/dieu-phoi/lenh-sx/'),
            {SX_LIST_QS_SESSION_KEY: {'/san-xuat/dieu-phoi/lenh-sx/': 'code=X'}},
        )
        ajax.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        ajax.META['HTTP_HOST'] = 'testserver'
        ajax.META['HTTP_REFERER'] = 'http://testserver/san-xuat/dieu-phoi/lenh-sx/1/'
        self.assertIsNone(maybe_redirect_sx_list_filters(ajax))

        detail = _with_session(self.factory.get('/san-xuat/dieu-phoi/lenh-sx/9/'))
        self.assertIsNone(maybe_redirect_sx_list_filters(detail))

    def test_npl_catalog_restores_after_back_from_detail(self):
        list_path = '/kho-npl/danh-muc/'
        filtered = _with_session(
            self.factory.get(list_path, {'q': 'vai', 'status': 'all'}),
        )
        self.assertIsNone(maybe_redirect_sx_list_filters(filtered))
        back = _with_session(
            self.factory.get(list_path),
            {SX_LIST_QS_SESSION_KEY: dict(filtered.session[SX_LIST_QS_SESSION_KEY])},
        )
        back.META['HTTP_HOST'] = 'testserver'
        back.META['HTTP_REFERER'] = 'http://testserver/kho-npl/danh-muc/4181/'
        response = maybe_redirect_sx_list_filters(back)
        self.assertIsNotNone(response)
        self.assertIn('q=vai', response['Location'])
        self.assertIn('status=all', response['Location'])

