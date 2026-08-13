from .models import ReportCommentAttachment


def _is_image_upload(uploaded) -> bool:
    name = (getattr(uploaded, 'name', '') or '').lower()
    if name.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx', '.zip', '.rar', '.7z')):
        return False
    content_type = (getattr(uploaded, 'content_type', '') or '').lower()
    if content_type.startswith('image/'):
        return True
    return name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.heic', '.heif'))


def save_comment_attachments(comment, uploaded_files):
    created = []
    for uploaded in uploaded_files or []:
        if not uploaded:
            continue
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
    return created
