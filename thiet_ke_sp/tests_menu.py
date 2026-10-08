from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from hrm.models import Profile
from thiet_ke_sp.models import ProductDevelopment, Status
from thiet_ke_sp.presenters import KANBAN_COLUMN_OF, KANBAN_COLUMNS, kanban_columns, kanban_moves_for_status

User = get_user_model()


def make_user(username, *, admin=False):
    user = User.objects.create_user(username=username, password='x')
    profile = Profile.objects.get(user=user)
    profile.must_change_password = False
    profile.save()
    if admin:
        User.objects.filter(pk=user.pk).update(is_superuser=True, is_staff=True)
    return User.objects.get(pk=user.pk)


class MenuPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('tksp_menu_admin', admin=True)
        call_command('seed_thiet_ke_sp_demo', user=cls.admin.username, stdout=StringIO())

    def setUp(self):
        self.client.force_login(self.admin)

    def _sidebar(self):
        body = self.client.get(reverse('thiet_ke_sp:dashboard')).content.decode()
        start = body.index('jp-sidebar-tksp-submenu')
        return body[start:body.index('</ul>', start)]

    def test_sidebar_lists_module_menus_in_demo_order(self):
        sidebar = self._sidebar()
        labels = ['Tổng quan', 'Hồ sơ sản phẩm', 'Tiến độ Kanban', 'Chờ tôi duyệt', 'Báo cáo']
        positions = [sidebar.index(f'<span>{label}</span>') for label in labels]
        self.assertEqual(positions, sorted(positions))

    def test_notifications_menu_removed_but_page_kept(self):
        self.assertNotIn('<span>Thông báo</span>', self._sidebar())
        body = self.client.get(reverse('thiet_ke_sp:list')).content.decode()
        self.assertNotIn(f'href="{reverse("thiet_ke_sp:notifications")}"', body)
        self.assertEqual(self.client.get(reverse('thiet_ke_sp:notifications')).status_code, 200)

    def test_kanban_renders_with_filters(self):
        url = reverse('thiet_ke_sp:kanban')
        for query in ('', '?quick=mine', '?quick=overdue', '?q=demo', '?group=bong_da'):
            resp = self.client.get(url + query)
            self.assertEqual(resp.status_code, 200, query)
        resp = self.client.get(url)
        self.assertContains(resp, 'tk-kan-col')
        self.assertContains(resp, 'data-movable="1"')
        self.assertContains(resp, 'id="tkKanMoveModal"')
        self.assertContains(resp, 'id="tkKanMoveSpecs"')
        self.assertGreater(resp.context['total_count'], 0)

    def test_kanban_columns_always_include_paused(self):
        cols = kanban_columns([])
        keys = [c['key'] for c in cols]
        self.assertIn('paused', keys)
        self.assertEqual(len(cols), len(KANBAN_COLUMNS))

    def test_reports_render_with_filters(self):
        url = reverse('thiet_ke_sp:reports')
        for query in ('', '?group=bong_da', '?collection=xyz', '?group=invalid'):
            resp = self.client.get(url + query)
            self.assertEqual(resp.status_code, 200, query)
        data = self.client.get(url).context['data']
        self.assertGreater(data['total'], 0)
        self.assertIn('revision_reasons', data)

    def test_approve_queue_title(self):
        resp = self.client.get(reverse('thiet_ke_sp:approve_queue'))
        self.assertContains(resp, 'Việc chờ tôi phê duyệt')

    def test_anonymous_redirected(self):
        self.client.logout()
        for name in ('kanban', 'reports'):
            resp = self.client.get(reverse(f'thiet_ke_sp:{name}'))
            self.assertEqual(resp.status_code, 302)


class KanbanMoveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('tksp_kanban_admin', admin=True)
        call_command('seed_thiet_ke_sp_demo', user=cls.admin.username, stdout=StringIO())

    def setUp(self):
        self.client.force_login(self.admin)

    def _dossier(self, status):
        return ProductDevelopment.objects.filter(status=status).order_by('pk').first()

    def _move(self, dossier, to, **extra):
        data = {'to': to, 'from': dossier.status, 'next': reverse('thiet_ke_sp:kanban'), **extra}
        return self.client.post(reverse('thiet_ke_sp:kanban_move', args=[dossier.pk]), data)

    def _levels(self, resp):
        return [m.level_tag for m in get_messages(resp.wsgi_request)]

    def test_brief_pending_to_design_approves_brief(self):
        d = self._dossier(Status.BRIEF_PENDING)
        resp = self._move(d, 'design')
        self.assertRedirects(resp, reverse('thiet_ke_sp:kanban'), fetch_redirect_response=False)
        d.refresh_from_db()
        self.assertEqual(d.status, Status.DESIGNING)
        self.assertIn('success', self._levels(resp))

    def test_brief_pending_back_to_proposal_requires_comment(self):
        d = self._dossier(Status.BRIEF_PENDING)
        resp = self._move(d, 'proposal')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.BRIEF_PENDING)
        self.assertIn('error', self._levels(resp))
        self._move(d, 'proposal', comment='Bổ sung bảng size')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.BRIEF_NEEDS_INFO)

    def test_skip_steps_is_rejected(self):
        d = self._dossier(Status.BRIEF_PENDING)
        resp = self._move(d, 'handover')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.BRIEF_PENDING)
        self.assertIn('error', self._levels(resp))

    def test_stale_from_status_is_rejected(self):
        d = self._dossier(Status.BRIEF_PENDING)
        resp = self.client.post(reverse('thiet_ke_sp:kanban_move', args=[d.pk]), {
            'to': 'design', 'from': Status.DRAFT, 'next': reverse('thiet_ke_sp:kanban'),
        })
        d.refresh_from_db()
        self.assertEqual(d.status, Status.BRIEF_PENDING)
        self.assertIn('error', self._levels(resp))

    def test_master_approve_requires_official_code(self):
        d = self._dossier(Status.MASTER_PENDING)
        resp = self._move(d, 'handover')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.MASTER_PENDING)
        self.assertIn('error', self._levels(resp))
        resp = self._move(d, 'handover', official_code='jp-kanban-0001')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.APPROVED)
        self.assertEqual(d.official_product_code, 'JP-KANBAN-0001')

    def test_pause_and_resume_by_drag(self):
        d = self._dossier(Status.DESIGN_PENDING)
        resp = self._move(d, 'paused')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.DESIGN_PENDING)
        self.assertIn('error', self._levels(resp))
        self._move(d, 'paused', comment='Chờ chốt BST')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.PAUSED)
        self.assertEqual(kanban_moves_for_status(d), {KANBAN_COLUMN_OF[Status.DESIGN_PENDING]: 'resume'})
        self._move(d, KANBAN_COLUMN_OF[Status.DESIGN_PENDING])
        d.refresh_from_db()
        self.assertEqual(d.status, Status.DESIGN_PENDING)

    def test_external_next_falls_back_to_kanban(self):
        d = self._dossier(Status.BRIEF_PENDING)
        resp = self._move(d, 'handover', next='https://example.com/')
        self.assertRedirects(resp, reverse('thiet_ke_sp:kanban'), fetch_redirect_response=False)

    def test_user_without_role_cannot_move(self):
        d = self._dossier(Status.BRIEF_PENDING)
        self.client.force_login(make_user('tksp_kanban_plain'))
        self._move(d, 'design')
        d.refresh_from_db()
        self.assertEqual(d.status, Status.BRIEF_PENDING)
