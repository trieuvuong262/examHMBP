import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.txt', '.csv',
}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def is_image_filename(name: str) -> bool:
    return os.path.splitext((name or '').lower())[1] in IMAGE_EXTENSIONS


def validate_attachment_file(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or 'file'
    ext = os.path.splitext(name.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'File "{name}" không được hỗ trợ. '
            'Chấp nhận: hình ảnh, PDF, Word, Excel, PowerPoint, ZIP, TXT.',
        )
    size = getattr(uploaded_file, 'size', 0) or 0
    if size > MAX_ATTACHMENT_SIZE:
        raise ValidationError(f'File "{name}" vượt quá 10 MB.')


def read_upload_files(file_list):
    """Đọc upload vào bộ nhớ để gán cho nhiều task."""
    prepared = []
    for uploaded in file_list:
        validate_attachment_file(uploaded)
        content = uploaded.read()
        prepared.append((uploaded.name, ContentFile(content, name=uploaded.name)))
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
