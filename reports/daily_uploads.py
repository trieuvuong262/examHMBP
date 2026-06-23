import os

from django.core.files.base import ContentFile

from .models import DailyWorkReportAttachment


def save_daily_uploads(
    report,
    *,
    bang_images=None,
    bang_files=None,
    vanban_images=None,
    vanban_files=None,
    link_images=None,
    link_files=None,
):
    """Lưu file/ảnh báo cáo VP — tab Bảng / Văn bản / Link."""
    created = []
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
