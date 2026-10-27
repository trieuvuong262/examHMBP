from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from kho_npl.doc_attachment import DOC_ATTACHMENT_MAX_BYTES
from kho_npl.forms import MaterialForm
from kho_npl.models import Material


class MaterialImageCleaningTests(SimpleTestCase):
    def setUp(self):
        # Isolate image cleaning from catalog querysets and historical migrations.
        self.material = Material(pk=4627, image='npl/materials/missing.png')
        self.form = MaterialForm.__new__(MaterialForm)
        self.form.instance = self.material

    def clean_image(self, value):
        self.form.cleaned_data = {'image': value}
        return self.form.clean_image()

    def test_unchanged_missing_image_does_not_read_storage_size(self):
        image = self.material.image
        # Match FileField.clean(): no upload means returning the initial file.
        value = MaterialForm.base_fields['image'].clean(None, initial=image)
        with patch.object(image.storage, 'size', side_effect=FileNotFoundError) as size:
            self.assertIs(self.clean_image(value), image)
        size.assert_not_called()

    def test_clear_missing_image(self):
        self.assertIs(self.clean_image(False), False)

    def test_new_upload_replaces_missing_image(self):
        upload = SimpleUploadedFile('new.png', b'image', content_type='image/png')
        self.assertIs(self.clean_image(upload), upload)

    def test_new_upload_with_invalid_extension_is_rejected(self):
        upload = SimpleUploadedFile('new.txt', b'not an image')
        with self.assertRaises(ValidationError):
            self.clean_image(upload)

    def test_oversized_new_upload_is_rejected(self):
        upload = SimpleUploadedFile('new.png', b'image', content_type='image/png')
        upload.size = DOC_ATTACHMENT_MAX_BYTES + 1
        with self.assertRaises(ValidationError):
            self.clean_image(upload)

    def test_new_material_without_image(self):
        self.form.instance = Material()
        self.assertIsNone(self.clean_image(None))
