import os

from django.core.files.base import ContentFile

from .models import DailyWorkReportAttachment


def _is_image_upload(uploaded) -> bool:
    name = (getattr(uploaded, 'name', '') or '').lower()
    if name.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx', '.zip', '.rar', '.7z')):
        return False
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type.startswith('image/'):
        return True
    return name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.heic', '.heif'))


def save_daily_uploads(
    report,
    *,
    attachments=None,
    bang_images=None,
    bang_files=None,
    vanban_images=None,
    vanban_files=None,
    link_images=None,
    link_files=None,
):
    """Lưu file/ảnh báo cáo VP — mặc định gộp vào tab Link."""
    created = []
    for uploaded in attachments or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_LINK,
                kind=(
                    DailyWorkReportAttachment.KIND_IMAGE
                    if _is_image_upload(uploaded)
                    else DailyWorkReportAttachment.KIND_FILE
                ),
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    for uploaded in bang_images or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_BANG,
                kind=DailyWorkReportAttachment.KIND_IMAGE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'image',
            ),
        )
    for uploaded in bang_files or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_BANG,
                kind=DailyWorkReportAttachment.KIND_FILE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    for uploaded in vanban_images or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_VANBAN,
                kind=DailyWorkReportAttachment.KIND_IMAGE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'image',
            ),
        )
    for uploaded in vanban_files or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_VANBAN,
                kind=DailyWorkReportAttachment.KIND_FILE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    for uploaded in link_images or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_LINK,
                kind=DailyWorkReportAttachment.KIND_IMAGE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'image',
            ),
        )
    for uploaded in link_files or []:
        created.append(
            DailyWorkReportAttachment.objects.create(
                report=report,
                source_tab=DailyWorkReportAttachment.SOURCE_LINK,
                kind=DailyWorkReportAttachment.KIND_FILE,
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    return created


def copy_daily_attachments(source_report, target_report):
    copied = []
    for att in source_report.attachments.all():
        name = att.original_name or os.path.basename(att.file.name)
        att.file.open('rb')
        try:
            content = att.file.read()
        finally:
            att.file.close()
        copied.append(
            DailyWorkReportAttachment.objects.create(
                report=target_report,
                source_tab=att.source_tab,
                kind=att.kind,
                file=ContentFile(content, name=name),
                original_name=name,
            ),
        )
    return copied
