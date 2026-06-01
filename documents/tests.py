from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from documents.knowledge_base import build_portal_knowledge
from documents.models import LibraryQAChatMessage
from documents.qa_history import save_qa_turn
from documents.suggestion_service import (
    generate_initial_suggestions,
    merge_suggestions,
    _filter_unique,
    _rule_based_suggestions,
)
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_DOCUMENTS
from hrm.permissions import ROLE_EMPLOYEE


class LibraryQATests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Test Dept')
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['documents'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    MODULE_DOCUMENTS: {'view': True, 'edit': False},
                },
            },
        )
        self.user = User.objects.create_user(username='libuser', password='pass1234')
        Profile.objects.filter(user=self.user).update(
            full_name='Lib User',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.user = User.objects.select_related('profile', 'profile__department').get(pk=self.user.pk)
        self.client = Client()
        self.client.force_login(self.user)
        self.factory = RequestFactory()

    def test_qa_page_requires_login(self):
        anon = Client()
        res = anon.get(reverse('documents:qa'))
        self.assertEqual(res.status_code, 302)

    def test_qa_page_loads(self):
        res = self.client.get(reverse('documents:qa'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Trợ lý AI JustPlay')

    def test_knowledge_includes_user_role(self):
        text = build_portal_knowledge(self.user)
        self.assertIn('Lib User', text)
        self.assertIn('Test Dept', text)

    def test_knowledge_includes_document_links(self):
        req = self.factory.get('/tai-lieu/hoi-dap/')
        text = build_portal_knowledge(self.user, request=req)
        self.assertIn('Link:', text)
        self.assertIn('/tai-lieu/', text)
        self.assertIn('quy-che-luong', text)

    def test_initial_suggestions_use_documents(self):
        req = self.factory.get('/tai-lieu/hoi-dap/')
        items = generate_initial_suggestions(self.user, request=req)
        self.assertGreaterEqual(len(items), 1)
        joined = ' '.join(items).lower()
        self.assertTrue(
            'quy chế' in joined or 'tài liệu' in joined or 'module' in joined or 'link' in joined
        )

    def test_rule_based_suggestions_after_salary_answer(self):
        req = self.factory.get('/tai-lieu/hoi-dap/')
        answer = 'Bạn có thể xem Quy chế lương trong nhóm Nhân sự trên portal.'
        items = _rule_based_suggestions(
            self.user,
            'Quy chế lương thế nào?',
            answer,
            history=[{'role': 'user', 'text': 'Quy chế lương thế nào?'}],
            request=req,
        )
        joined = ' '.join(items)
        self.assertIn('Quy chế lương', joined)

    def test_filter_unique_avoids_exact_repeat(self):
        history = [{'role': 'user', 'text': 'Quy chế lương thế nào?'}]
        out = _filter_unique(
            ['Quy chế lương thế nào?', 'Gửi link Quy chế lương?', 'Quy trình an toàn gồm mấy bước?'],
            history,
        )
        self.assertEqual(len(out), 2)
        self.assertIn('Gửi link Quy chế lương?', out)
        self.assertIn('Quy trình', out[1])

    def test_merge_suggestions_prefers_ai_then_rules(self):
        history = [{'role': 'user', 'text': 'Xin chào'}]
        out = merge_suggestions(
            ['Chi tiết quy trình nộp báo cáo?'],
            ['Gửi link Quy chế lương?', 'Ai phê duyệt yêu cầu?'],
            history,
            limit=3,
        )
        self.assertEqual(len(out), 3)

    @patch('documents.views.generate_followup_suggestions', return_value=['Chi tiết thêm về quy trình này?'])
    @patch('documents.views.ask_portal_assistant', return_value='Trả lời mẫu.')
    def test_qa_ask_api(self, mock_ask, mock_suggest):
        res = self.client.post(
            reverse('documents:qa_ask'),
            data='{"question":"Xin chào"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['answer'], 'Trả lời mẫu.')
        self.assertEqual(data['suggestions'], ['Chi tiết thêm về quy trình này?'])
        mock_ask.assert_called_once()
        mock_suggest.assert_called_once()
        self.assertEqual(LibraryQAChatMessage.objects.filter(user=self.user).count(), 2)

    @patch('documents.views.ask_portal_assistant', return_value='Câu trả lời.')
    def test_qa_history_persists_and_reloads(self, mock_ask):
        save_qa_turn(self.user, 'Câu cũ?', 'Trả lời cũ.')
        from documents.qa_history import get_user_qa_history_for_display

        stored = get_user_qa_history_for_display(self.user)
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored[0]['text'], 'Câu cũ?')

        res = self.client.get(reverse('documents:qa'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="qa-history-data"')


class DocumentSourceFileTests(TestCase):
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from documents.models import Document, DocumentCategory

        self.dept = Department.objects.create(name='HR Dept')
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['documents'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    MODULE_DOCUMENTS: {'view': True, 'edit': False},
                },
            },
        )
        self.user = User.objects.create_user(username='docuser', password='pass1234')
        Profile.objects.filter(user=self.user).update(
            full_name='Doc User',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.category = DocumentCategory.objects.create(
            name='Nhân sự',
            slug='nhan-su-test',
            is_active=True,
        )
        self.pdf_bytes = b'%PDF-1.4 test'
        self.pdf_upload = SimpleUploadedFile('quy-che.pdf', self.pdf_bytes, content_type='application/pdf')
        self.doc = Document.objects.create(
            category=self.category,
            title='Quy chế test',
            slug='quy-che-test',
            content_type=Document.TYPE_TEXT,
            body='<p>Nội dung tóm tắt trên portal.</p>',
            original_file=self.pdf_upload,
            is_active=True,
        )

    def test_browse_shows_original_file_actions(self):
        url = reverse('documents:browse_document', args=[self.category.slug, self.doc.slug])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Tài liệu gốc')
        self.assertContains(res, 'Tải về')
        self.assertContains(res, 'quy-che.pdf')

    def test_download_requires_login(self):
        url = reverse('documents:file_download', args=[self.doc.pk])
        anon = Client()
        res = anon.get(url)
        self.assertEqual(res.status_code, 302)

    def test_authenticated_user_can_download_original(self):
        url = reverse('documents:file_download', args=[self.doc.pk])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment', res.get('Content-Disposition', ''))
        self.assertEqual(b''.join(res.streaming_content), self.pdf_bytes)
