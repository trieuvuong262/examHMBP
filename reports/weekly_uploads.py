import os

from django.core.files.base import ContentFile

from .models import WeeklyWorkReportAttachment


def save_weekly_uploads(report, *, image_list=None, file_list=None):
    """Lưu file/ảnh báo cáo tuần — không giới hạn kích thước ở tầng ứng dụng."""
    created = []
    for uploaded in image_list or []:
        created.append(
            WeeklyWorkReportAttachment.objects.create(
                report=report,
                kind=WeeklyWorkReportAttachment.KIND_IMAGE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'image',
            ),
        )
    for uploaded in file_list or []:
        created.append(
            WeeklyWorkReportAttachment.objects.create(
                report=report,
                kind=WeeklyWorkReportAttachment.KIND_FILE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    return created


def copy_weekly_attachments(source_report, target_report):
    copied = []
    for att in source_report.attachments.all():
        name = att.original_name or os.path.basename(att.file.name)
        att.file.open('rb')
        try:
            content = att.file.read()
        finally:
            att.file.close()
        copied.append(
            WeeklyWorkReportAttachment.objects.create(
                report=target_report,
                kind=att.kind,
                file=ContentFile(content, name=name),
                original_name=name,
            ),
        )
    return copied


def weekly_report_has_content(*, links_text, image_uploads, file_uploads, attachment_count):
    if (links_text or '').strip():
        return True
    if image_uploads or file_uploads:
        return True
    return attachment_count > 0
