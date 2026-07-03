"""Upload chứng từ / ảnh đính kèm phiếu kho NPL."""
import os

from django import forms
from django.core.exceptions import ValidationError
from django.forms.widgets import FILE_INPUT_CONTRADICTION, CheckboxInput

DOC_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
DOC_ATTACHMENT_EXTENSIONS = {
    '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.doc', '.docx', '.xls', '.xlsx',
}
DOC_ATTACHMENT_ACCEPT = 'image/*,.pdf,.doc,.docx,.xls,.xlsx'
IMAGE_ATTACHMENT_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def validate_doc_attachment(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    if ext not in DOC_ATTACHMENT_EXTENSIONS:
        raise ValidationError('File không hợp lệ.')
    if uploaded_file.size > DOC_ATTACHMENT_MAX_BYTES:
        raise ValidationError('File không hợp lệ.')
    return uploaded_file


DOC_ATTACHMENT_REQUIRED_MSG = 'Vui lòng đính kèm chứng từ.'
DOC_ATTACHMENT_CLEAR_MSG = 'Đã xóa chứng từ — vui lòng chọn file mới trước khi lưu.'


def clean_required_doc_attachment(cleaned_data, instance, *, field: str = 'attachment'):
    """Upload / giữ chứng từ; xóa mà không thay file mới thì không cho lưu."""
    uploaded = cleaned_data.get(field)
    if uploaded is False:
        raise ValidationError(DOC_ATTACHMENT_CLEAR_MSG)
    if uploaded:
        return validate_doc_attachment(uploaded)
    if instance.pk and getattr(instance, field, None):
        return getattr(instance, field)
    raise ValidationError(DOC_ATTACHMENT_REQUIRED_MSG)


def doc_attachment_required(instance, *, field: str = 'attachment') -> bool:
    file_field = getattr(instance, field, None)
    return bool(file_field and getattr(file_field, 'name', ''))


def attachment_is_image(file_field) -> bool:
    if not file_field:
        return False
    ext = os.path.splitext(file_field.name or '')[1].lower()
    return ext in IMAGE_ATTACHMENT_EXTENSIONS


def can_replace_doc_attachment(*, is_editable: bool, posted_editable: bool, can_update: bool) -> bool:
    """Nháp (sửa phiếu) hoặc đã ghi sổ (sửa ghi chú) — cần quyền cập nhật."""
    return bool(can_update and (is_editable or posted_editable))


def replace_doc_attachment(instance, uploaded, *, field: str = 'attachment') -> None:
    old = getattr(instance, field, None)
    old_name = getattr(old, 'name', '') if old else ''
    setattr(instance, field, uploaded)
    instance.save(update_fields=[field])
    if old_name and (not getattr(instance, field) or getattr(instance, field).name != old_name):
        old.delete(save=False)


class DocClearableFileInput(forms.ClearableFileInput):
    template_name = 'kho_npl/widgets/doc_clearable_file_input.html'
    clear_checkbox_label = 'Xóa'
    initial_text = 'Hiện tại'
    input_text = 'Chọn file mới'

    def value_from_datadict(self, data, files, name):
        upload = forms.FileInput.value_from_datadict(self, data, files, name)
        clear_name = self.clear_checkbox_name(name)
        self.checked = clear_name in data
        if CheckboxInput().value_from_datadict(data, files, clear_name):
            if upload:
                return FILE_INPUT_CONTRADICTION
            return False
        return upload
