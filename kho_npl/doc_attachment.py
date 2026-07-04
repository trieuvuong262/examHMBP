"""Upload chứng từ / ảnh đính kèm phiếu kho NPL."""
import os
from dataclasses import dataclass

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms.widgets import FILE_INPUT_CONTRADICTION, CheckboxInput

DOC_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
DOC_ATTACHMENT_EXTENSIONS = {
    '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.doc', '.docx', '.xls', '.xlsx',
}
DOC_ATTACHMENT_ACCEPT = 'image/*,.pdf,.doc,.docx,.xls,.xlsx'
IMAGE_ATTACHMENT_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
DOC_ATTACHMENT_FIELD_NAME = 'attachments'
DOC_ATTACHMENT_MAX_COUNT = 20


def validate_doc_attachment(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    ext = os.path.splitext(uploaded_file.name or '')[1].lower()
    if ext not in DOC_ATTACHMENT_EXTENSIONS:
        raise ValidationError('File không hợp lệ.')
    if uploaded_file.size > DOC_ATTACHMENT_MAX_BYTES:
        raise ValidationError('File không hợp lệ.')
    return uploaded_file


def validate_doc_attachment_list(files):
    if not files:
        return []
    if len(files) > DOC_ATTACHMENT_MAX_COUNT:
        raise ValidationError(f'Tối đa {DOC_ATTACHMENT_MAX_COUNT} file mỗi lần tải.')
    return [validate_doc_attachment(uploaded) for uploaded in files]


DOC_ATTACHMENT_REQUIRED_MSG = 'Vui lòng đính kèm chứng từ.'
DOC_ATTACHMENT_CLEAR_MSG = 'Đã xóa chứng từ — vui lòng chọn file mới trước khi lưu.'


@dataclass(frozen=True)
class LegacyDocAttachment:
    pk: None
    file: object


def _content_type_for(instance):
    return ContentType.objects.get_for_model(instance.__class__)


def _attachment_queryset(instance):
    from kho_npl.models import NplDocAttachment

    if not instance.pk:
        return NplDocAttachment.objects.none()
    ct = _content_type_for(instance)
    return NplDocAttachment.objects.filter(content_type=ct, object_id=instance.pk)


def doc_attachments_for(instance):
    """Danh sách chứng từ — ưu tiên bảng NplDocAttachment, fallback field cũ."""
    if not instance.pk:
        return []
    qs = list(_attachment_queryset(instance).order_by('uploaded_at', 'pk'))
    if qs:
        return qs
    legacy = getattr(instance, 'attachment', None)
    if legacy and getattr(legacy, 'name', ''):
        return [LegacyDocAttachment(pk=None, file=legacy)]
    return []


def doc_attachment_count(instance) -> int:
    return len(doc_attachments_for(instance))


def doc_has_attachments(instance) -> bool:
    return doc_attachment_count(instance) > 0


def sync_legacy_attachment_field(instance, *, field: str = 'attachment') -> None:
    """Giữ field attachment cũ trỏ tới file đầu tiên (tương thích ngược)."""
    if not hasattr(instance, field):
        return
    attachments = _attachment_queryset(instance).order_by('uploaded_at', 'pk')
    first = attachments.first()
    current = getattr(instance, field, None)
    if first:
        if not current or current.name != first.file.name:
            setattr(instance, field, first.file)
            instance.save(update_fields=[field])
    elif current and getattr(current, 'name', ''):
        setattr(instance, field, '')
        instance.save(update_fields=[field])


def ensure_legacy_attachment_migrated(instance, *, uploaded_by=None) -> None:
    if _attachment_queryset(instance).exists():
        return
    legacy = getattr(instance, 'attachment', None)
    if not legacy or not getattr(legacy, 'name', ''):
        return
    from kho_npl.models import NplDocAttachment

    NplDocAttachment.objects.create(
        content_type=_content_type_for(instance),
        object_id=instance.pk,
        file=legacy,
        uploaded_by=uploaded_by,
    )


def add_doc_attachments(instance, files, *, uploaded_by=None) -> int:
    if not instance.pk:
        raise ValueError('Instance must be saved before adding attachments.')
    files = validate_doc_attachment_list(files)
    if not files:
        return 0
    ensure_legacy_attachment_migrated(instance, uploaded_by=uploaded_by)
    from kho_npl.models import NplDocAttachment

    ct = _content_type_for(instance)
    existing = _attachment_queryset(instance).count()
    if existing + len(files) > DOC_ATTACHMENT_MAX_COUNT:
        raise ValidationError(f'Tối đa {DOC_ATTACHMENT_MAX_COUNT} chứng từ mỗi phiếu.')
    created = []
    for uploaded in files:
        created.append(NplDocAttachment.objects.create(
            content_type=ct,
            object_id=instance.pk,
            file=uploaded,
            uploaded_by=uploaded_by,
        ))
    sync_legacy_attachment_field(instance)
    return len(created)


def delete_doc_attachment(attachment, *, parent=None) -> None:
    from kho_npl.models import NplDocAttachment

    if not isinstance(attachment, NplDocAttachment):
        raise ValidationError('Không thể xóa chứng từ này.')
    parent = parent or attachment.content_object
    attachment.file.delete(save=False)
    attachment.delete()
    if parent:
        sync_legacy_attachment_field(parent)


def attachment_files_from_request(files) -> list:
    if not files:
        return []
    return [uploaded for uploaded in files.getlist(DOC_ATTACHMENT_FIELD_NAME) if uploaded]


def clean_required_doc_attachment(cleaned_data, instance, *, field: str = 'attachment'):
    """Upload / giữ chứng từ; xóa mà không thay file mới thì không cho lưu."""
    uploaded = cleaned_data.get(field)
    if uploaded is False:
        raise ValidationError(DOC_ATTACHMENT_CLEAR_MSG)
    if uploaded:
        return validate_doc_attachment(uploaded)
    if doc_has_attachments(instance):
        return getattr(instance, field, None)
    if instance.pk and getattr(instance, field, None):
        return getattr(instance, field)
    raise ValidationError(DOC_ATTACHMENT_REQUIRED_MSG)


def doc_attachment_required(instance, *, field: str = 'attachment') -> bool:
    return doc_has_attachments(instance) or bool(
        getattr(instance, field, None) and getattr(getattr(instance, field, None), 'name', '')
    )


def attachment_is_image(file_field) -> bool:
    if not file_field:
        return False
    ext = os.path.splitext(file_field.name or '')[1].lower()
    return ext in IMAGE_ATTACHMENT_EXTENSIONS


def can_replace_doc_attachment(*, is_editable: bool, posted_editable: bool, can_update: bool) -> bool:
    """Nháp (sửa phiếu) hoặc đã ghi sổ (sửa ghi chú) — cần quyền cập nhật."""
    return bool(can_update and (is_editable or posted_editable))


def replace_doc_attachment(instance, uploaded, *, field: str = 'attachment') -> None:
    add_doc_attachments(instance, [uploaded])


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


class DocMultipleFileInput(forms.FileInput):
    template_name = 'kho_npl/widgets/doc_multiple_file_input.html'
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'accept': DOC_ATTACHMENT_ACCEPT,
            'multiple': True,
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def value_from_datadict(self, data, files, name):
        return files.getlist(name) if files else []
