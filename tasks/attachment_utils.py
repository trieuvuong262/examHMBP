import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
DOCUMENT_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.txt', '.csv',
}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def is_image_filename(name: str) -> bool:
    return os.path.splitext((name or '').lower())[1] in IMAGE_EXTENSIONS


def _check_file_size(uploaded_file, name: str):
    size = getattr(uploaded_file, 'size', 0) or 0
    if size > MAX_ATTACHMENT_SIZE:
        raise ValidationError(f'File "{name}" vượt quá 10 MB.')


def validate_image_file(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or 'file'
    ext = os.path.splitext(name.lower())[1]
    if ext not in IMAGE_EXTENSIONS:
        raise ValidationError(f'"{name}" không phải hình ảnh. Chọn file JPG, PNG, GIF hoặc WebP.')
    _check_file_size(uploaded_file, name)


def validate_document_file(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or 'file'
    ext = os.path.splitext(name.lower())[1]
    if ext in IMAGE_EXTENSIONS:
        raise ValidationError(f'"{name}" là hình ảnh — dùng ô tải hình ảnh riêng.')
    if ext not in DOCUMENT_EXTENSIONS:
        raise ValidationError(
            f'File "{name}" không được hỗ trợ. '
            'Chấp nhận: PDF, Word, Excel, PowerPoint, ZIP, TXT.',
        )
    _check_file_size(uploaded_file, name)


def validate_attachment_file(uploaded_file):
    """Tương thích cũ — chấp nhận cả ảnh và file."""
    name = getattr(uploaded_file, 'name', '') or 'file'
    ext = os.path.splitext(name.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'File "{name}" không được hỗ trợ. '
            'Chấp nhận: hình ảnh, PDF, Word, Excel, PowerPoint, ZIP, TXT.',
        )
    _check_file_size(uploaded_file, name)


def _read_file_list(file_list, validator):
    prepared = []
    for uploaded in file_list:
        validator(uploaded)
        content = uploaded.read()
        prepared.append((uploaded.name, ContentFile(content, name=uploaded.name)))
    return prepared


def read_separate_uploads(image_list, file_list):
    """Đọc hình ảnh và file tài liệu từ hai ô upload riêng."""
    prepared = []
    prepared.extend(_read_file_list(image_list, validate_image_file))
    prepared.extend(_read_file_list(file_list, validate_document_file))
    return prepared


def save_task_attachments(task, prepared_files, *, uploaded_by, stage):
    from .models import WorkTaskAttachment

    created = []
    for original_name, content_file in prepared_files:
        att = WorkTaskAttachment.objects.create(
            task=task,
            file=content_file,
            original_name=original_name,
            uploaded_by=uploaded_by,
            stage=stage,
        )
        created.append(att)
    return created


def save_recurrence_attachments(recurrence, prepared_files, *, uploaded_by):
    from .models import WorkTaskRecurrenceAttachment

    created = []
    for original_name, content_file in prepared_files:
        att = WorkTaskRecurrenceAttachment.objects.create(
            recurrence=recurrence,
            file=content_file,
            original_name=original_name,
            uploaded_by=uploaded_by,
        )
        created.append(att)
    return created


def copy_recurrence_attachments_to_task(recurrence, target_task, *, uploaded_by=None):
    from .models import WorkTaskAttachment

    copied = []
    for att in recurrence.attachments.all():
        att.file.open('rb')
        try:
            content = att.file.read()
        finally:
            att.file.close()
        name = att.display_name
        copied.append(
            WorkTaskAttachment.objects.create(
                task=target_task,
                file=ContentFile(content, name=name),
                original_name=name,
                uploaded_by=uploaded_by or att.uploaded_by,
                stage=WorkTaskAttachment.STAGE_ASSIGN,
            ),
        )
    return copied


def copy_task_attachments(source_task, target_task, *, stages=None, uploaded_by=None):
    from .models import WorkTaskAttachment

    qs = source_task.attachments.select_related('uploaded_by').all()
    if stages is not None:
        qs = qs.filter(stage__in=stages)

    copied = []
    for att in qs:
        att.file.open('rb')
        try:
            content = att.file.read()
        finally:
            att.file.close()
        name = att.original_name or os.path.basename(att.file.name)
        copied.append(
            WorkTaskAttachment.objects.create(
                task=target_task,
                file=ContentFile(content, name=name),
                original_name=name,
                uploaded_by=uploaded_by or att.uploaded_by,
                stage=att.stage,
            ),
        )
    return copied
