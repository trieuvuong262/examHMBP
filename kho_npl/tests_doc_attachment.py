from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from kho_npl.models import StockReceipt

from kho_npl.doc_attachment import clean_required_doc_attachment, DOC_ATTACHMENT_CLEAR_MSG, validate_doc_attachment


class DocAttachmentValidationTests(SimpleTestCase):
    def test_accepts_pdf(self):
        f = SimpleUploadedFile('chung-tu.pdf', b'%PDF-1.4', content_type='application/pdf')
        self.assertEqual(validate_doc_attachment(f), f)

    def test_accepts_jpeg(self):
        f = SimpleUploadedFile('anh.jpg', b'fake', content_type='image/jpeg')
        self.assertEqual(validate_doc_attachment(f), f)

    def test_rejects_unknown_extension(self):
        f = SimpleUploadedFile('virus.exe', b'bad', content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_doc_attachment(f)

    def test_rejects_oversize(self):
        f = SimpleUploadedFile('big.pdf', b'x' * (10 * 1024 * 1024 + 1), content_type='application/pdf')
        with self.assertRaises(ValidationError):
            validate_doc_attachment(f)
from kho_npl.doc_attachment import clean_required_doc_attachment, DOC_ATTACHMENT_CLEAR_MSG
from kho_npl.models import StockReceipt


class CleanRequiredDocAttachmentTests(SimpleTestCase):
    def test_clear_without_replacement_rejected(self):
        receipt = StockReceipt(pk=1)
        receipt.attachment = 'npl/receipts/attachments/old.pdf'
        with self.assertRaisesMessage(ValidationError, DOC_ATTACHMENT_CLEAR_MSG):
            clean_required_doc_attachment({'attachment': False}, receipt)

    def test_keep_existing_when_unchanged(self):
        receipt = StockReceipt(pk=1)
        receipt.attachment = 'npl/receipts/attachments/old.pdf'
        self.assertEqual(
            clean_required_doc_attachment({'attachment': None}, receipt),
            receipt.attachment,
        )

