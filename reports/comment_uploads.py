from .models import ReportCommentAttachment


def _is_image_upload(uploaded) -> bool:
    name = (getattr(uploaded, 'name', '') or '').lower()
    if name.endswith((
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx',
        '.zip', '.rar', '.7z',
        '.psd', '.psb', '.ai', '.eps', '.indd', '.idml', '.cdr',
        '.sketch', '.xd', '.fig', '.afdesign', '.afphoto', '.afpub',
    )):
        return False
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type.startswith('image/'):
        return True
    # .svg đã bị loại khỏi whitelist upload (nas_storage/upload_guard.py) nên
    # nhánh này không còn nhận SVG; giữ lại để phân loại dữ liệu cũ.
    return name.endswith((
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg',
        '.heic', '.heif', '.tif', '.tiff',
    ))


def save_comment_attachments(comment, uploaded_files, *, request=None):
    """Lưu đính kèm nhận xét — chỉ file hợp lệ; trả ``rejected`` để hiện popup."""
    from nas_storage.upload_guard import partition_uploads, upload_audit

    with upload_audit(request):
        accepted, rejected = partition_uploads(uploaded_files)

    created = []
    for uploaded in accepted:
        created.append(
            ReportCommentAttachment.objects.create(
                comment=comment,
                kind=(
                    ReportCommentAttachment.KIND_IMAGE
                    if _is_image_upload(uploaded)
                    else ReportCommentAttachment.KIND_FILE
                ),
                file=uploaded,
                original_name=getattr(uploaded, 'name', '') or 'file',
            ),
        )
    return created, rejected
