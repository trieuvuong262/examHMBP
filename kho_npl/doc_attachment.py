"""Upload chứng từ / ảnh đính kèm phiếu kho NPL."""
import os

from django.core.exceptions import ValidationError

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
        raise ValidationError(
            'Chỉ chấp nhận file PDF, Word, Excel hoặc ảnh (JPG, PNG, GIF, WEBP).',
        )
    if uploaded_file.size > DOC_ATTACHMENT_MAX_BYTES:
        raise ValidationError('File chứng từ không được lớn hơn 10MB.')
    return uploaded_file


def attachment_is_image(file_field) -> bool:
    if not file_field:
        return False
    ext = os.path.splitext(file_field.name or '')[1].lower()
    return ext in IMAGE_ATTACHMENT_EXTENSIONS
