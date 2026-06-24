from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image
from reportlab.pdfgen import canvas

from tools.catalog import PORTAL_TOOLS, get_portal_tool_groups
from tools.models import UserNote
from tools.services import (
    apply_image_watermark,
    compress_image,
    convert_image_format,
    convert_pdf_to_docx,
    generate_qr_image,
)


class ToolsCatalogTests(TestCase):
    def test_portal_has_ten_tools(self):
        self.assertEqual(len(PORTAL_TOOLS), 10)
        slugs = {tool['slug'] for tool in PORTAL_TOOLS}
        self.assertEqual(slugs, {
            'pdf-word',
            'office-pdf',
            'ocr',
            'compress',
            'convert-format',
            'watermark',
            'remove-bg',
            'qr',
            'notes',
            'schedule-reminder',
        })

    def test_portal_tool_groups_cover_all_tools(self):
        groups = get_portal_tool_groups()
        self.assertEqual(len(groups), 3)
        total = sum(len(group['tools']) for group in groups)
        self.assertEqual(total, len(PORTAL_TOOLS))


class ToolsServiceTests(TestCase):
    def test_generate_qr_requires_content(self):
        with self.assertRaises(ValidationError):
            generate_qr_image('   ')

    def test_generate_qr_png(self):
        png = generate_qr_image('https://justplay.vn')
        self.assertTrue(png.startswith(b'\x89PNG'))

    def test_compress_image_jpeg(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not available')

        buffer = BytesIO()
        Image.new('RGB', (800, 600), color=(220, 38, 38)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('test.jpg', buffer.getvalue(), content_type='image/jpeg')
        data, filename, content_type = compress_image(uploaded, quality=60, max_width=400)
        self.assertIn('nen', filename)
        self.assertEqual(content_type, 'image/jpeg')
        self.assertGreater(len(data), 0)

    def test_convert_image_format_to_webp(self):
        buffer = BytesIO()
        Image.new('RGB', (120, 80), color=(10, 120, 200)).save(buffer, format='PNG')
        uploaded = SimpleUploadedFile('src.png', buffer.getvalue(), content_type='image/png')
        data, filename, content_type = convert_image_format(uploaded, 'webp', quality=80)
        self.assertTrue(filename.endswith('.webp'))
        self.assertEqual(content_type, 'image/webp')
        self.assertGreater(len(data), 0)

    def test_apply_image_watermark_text(self):
        buffer = BytesIO()
        Image.new('RGB', (400, 300), color=(40, 40, 40)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('photo.jpg', buffer.getvalue(), content_type='image/jpeg')
        data, filename, content_type = apply_image_watermark(
            uploaded,
            text='JustPlay Test',
            position='center',
            opacity=40,
        )
        self.assertTrue(filename.endswith('-watermark.png'))
        self.assertEqual(content_type, 'image/png')
        self.assertTrue(data.startswith(b'\x89PNG'))


class ToolsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tooluser', password='pass12345')
        self.client = Client()
        self.client.login(username='tooluser', password='pass12345')

    def test_home_shows_tool_cards(self):
        response = self.client.get(reverse('home_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-home-tools-group')
        self.assertContains(response, 'Tài liệu')
        self.assertContains(response, 'PDF → Word')
        self.assertContains(response, 'Watermark ảnh')
        self.assertContains(response, 'Ghi chú')
        self.assertContains(response, 'Nhắc lịch')
        self.assertContains(response, 'Nhắc việc cá nhân')

    def test_tool_pages_require_login(self):
        self.client.logout()
        response = self.client.get(reverse('tools:ocr'))
        self.assertEqual(response.status_code, 302)

    def test_notes_create_and_api(self):
        response = self.client.post(reverse('tools:note_quick_add'), {
            'title': 'Việc IT',
            'content': 'Kiểm tra máy in',
            'color': 'blue',
        })
        self.assertEqual(response.status_code, 302)
        note = UserNote.objects.get(user=self.user)
        self.assertEqual(note.title, 'Việc IT')

        api_response = self.client.get(reverse('tools:notes_api'))
        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertEqual(len(payload['notes']), 1)

    def test_qr_preview_page(self):
        response = self.client.post(reverse('tools:qr_generator'), {
            'qr_data': 'hello',
            'box_size': 8,
            'border': 2,
            'action': 'preview',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data:image/png;base64,')


class ToolsIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tooluser2', password='pass12345')
        self.client = Client()
        self.client.login(username='tooluser2', password='pass12345')

    def test_all_tool_pages_load(self):
        for url_name in [
            'tools:pdf_to_word',
            'tools:office_to_pdf',
            'tools:ocr',
            'tools:compress_image',
            'tools:convert_image_format',
            'tools:watermark_image',
            'tools:remove_background',
            'tools:qr_generator',
            'tools:notes',
            'tools:schedule_reminder',
        ]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_qr_download(self):
        response = self.client.post(reverse('tools:qr_generator'), {
            'qr_data': 'https://justplay.vn',
            'box_size': 10,
            'border': 2,
            'action': 'download',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_compress_image_download(self):
        buffer = BytesIO()
        Image.new('RGB', (1200, 800), color=(30, 144, 255)).save(buffer, format='JPEG', quality=95)
        original_size = len(buffer.getvalue())
        uploaded = SimpleUploadedFile('big.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('tools:compress_image'), {
            'image_file': uploaded,
            'quality': 50,
            'max_width': 600,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/jpeg', response['Content-Type'])
        self.assertLess(len(response.content), original_size)

    def test_pdf_to_word_download(self):
        pdf_buffer = BytesIO()
        pdf_canvas = canvas.Canvas(pdf_buffer)
        pdf_canvas.drawString(100, 750, 'Hello JustPlay PDF test')
        pdf_canvas.save()
        uploaded = SimpleUploadedFile('test.pdf', pdf_buffer.getvalue(), content_type='application/pdf')
        response = self.client.post(reverse('tools:pdf_to_word'), {'pdf_file': uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertIn('wordprocessingml', response['Content-Type'])
        self.assertTrue(response.content.startswith(b'PK'))

    def test_pdf_to_word_accepts_missing_content_type(self):
        pdf_buffer = BytesIO()
        pdf_canvas = canvas.Canvas(pdf_buffer)
        pdf_canvas.drawString(100, 750, 'No content type')
        pdf_canvas.save()
        uploaded = SimpleUploadedFile('test.pdf', pdf_buffer.getvalue(), content_type='')
        docx_bytes, _filename = convert_pdf_to_docx(uploaded)
        self.assertTrue(docx_bytes.startswith(b'PK'))

    def test_pdf_to_word_with_real_pdf_file(self):
        pdf_path = Path(__file__).resolve().parent.parent / 'media' / 'tasks' / 'attachments' / '2026' / '05' / 'spec.pdf'
        if not pdf_path.exists() or pdf_path.stat().st_size < 100:
            self.skipTest('Sample PDF not available or too small')
        with pdf_path.open('rb') as handle:
            uploaded = SimpleUploadedFile('spec.pdf', handle.read(), content_type='application/pdf')
        response = self.client.post(reverse('tools:pdf_to_word'), {'pdf_file': uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'PK'))

    def test_notes_patch_and_delete(self):
        note = UserNote.objects.create(user=self.user, title='Old', content='Body', color='yellow')
        response = self.client.patch(
            reverse('tools:note_detail_api', args=[note.pk]),
            data='{"title":"New","content":"Updated body","color":"pink"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.title, 'New')
        self.assertEqual(note.color, 'pink')

        response = self.client.delete(reverse('tools:note_detail_api', args=[note.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserNote.objects.filter(pk=note.pk).exists())

    def test_client_side_tool_templates(self):
        ocr_response = self.client.get(reverse('tools:ocr'))
        self.assertContains(ocr_response, 'jpToolLoading')
        self.assertContains(ocr_response, 'tesseract.min.js')
        self.assertContains(ocr_response, 'ocr.js')

        rmbg_response = self.client.get(reverse('tools:remove_background'))
        self.assertContains(rmbg_response, 'remove_bg.js')
        self.assertContains(rmbg_response, reverse('tools:remove_background_api'))

    @patch('tools.views.remove_image_background')
    def test_remove_background_api_returns_png(self, mock_remove):
        mock_remove.return_value = (b'\x89PNG\r\n\x1a\nfake', 'portrait-khong-nen.png')
        buffer = BytesIO()
        Image.new('RGB', (64, 64), color=(255, 0, 0)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('portrait.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('tools:remove_background_api'), {'image_file': uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_convert_image_format_download(self):
        buffer = BytesIO()
        Image.new('RGB', (200, 200), color=(255, 128, 0)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('pic.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('tools:convert_image_format'), {
            'image_file': uploaded,
            'target_format': 'png',
            'quality': 85,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_watermark_image_download(self):
        buffer = BytesIO()
        Image.new('RGB', (300, 200), color=(0, 0, 128)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('brand.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('tools:watermark_image'), {
            'image_file': uploaded,
            'watermark_text': 'JustPlay',
            'position': 'bottom-right',
            'opacity': 30,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')

    @patch('tools.views.convert_office_to_pdf')
    def test_office_to_pdf_download(self, mock_convert):
        mock_convert.return_value = (b'%PDF-1.4 fake', 'report.pdf')
        uploaded = SimpleUploadedFile(
            'report.docx',
            b'fake-docx',
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        response = self.client.post(reverse('tools:office_to_pdf'), {'office_file': uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_remove_background_api_requires_file(self):
        response = self.client.post(reverse('tools:remove_background_api'), {})
        self.assertEqual(response.status_code, 400)

    @patch('tools.views.is_background_removal_ready', return_value=False)
    @patch('tools.views.remove_image_background', side_effect=Exception('boom'))
    def test_remove_background_api_warming_returns_retry(self, _remove, _ready):
        buffer = BytesIO()
        Image.new('RGB', (32, 32), color=(0, 255, 0)).save(buffer, format='JPEG')
        uploaded = SimpleUploadedFile('x.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client.post(reverse('tools:remove_background_api'), {'image_file': uploaded})
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertTrue(payload.get('retry'))
        self.assertTrue(payload.get('warming'))
