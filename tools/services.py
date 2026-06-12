import io
import os
import tempfile

import qrcode
from django.core.exceptions import ValidationError
from PIL import Image


PDF_MAX_BYTES = 10 * 1024 * 1024
IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

_bg_session = None


def _validate_pdf(uploaded_file):
    if uploaded_file.size > PDF_MAX_BYTES:
        raise ValidationError('File PDF tối đa 10 MB.')
    name = (uploaded_file.name or '').lower()
    if not name.endswith('.pdf'):
        raise ValidationError('Vui lòng chọn file PDF.')
    if uploaded_file.content_type and uploaded_file.content_type not in (
        'application/pdf',
        'application/x-pdf',
        'application/octet-stream',
    ):
        raise ValidationError('Định dạng file không hợp lệ.')


def _validate_image(uploaded_file):
    if uploaded_file.size > IMAGE_MAX_BYTES:
        raise ValidationError('Ảnh tối đa 10 MB.')
    if uploaded_file.content_type and uploaded_file.content_type not in IMAGE_TYPES:
        raise ValidationError('Chỉ hỗ trợ JPG, PNG, WebP hoặc GIF.')


def convert_pdf_to_docx(uploaded_file) -> tuple[bytes, str]:
    """Chuyển PDF sang DOCX — trả về (bytes, tên file gợi ý)."""
    _validate_pdf(uploaded_file)
    from pdf2docx import Converter

    base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'document.pdf'))[0]
    output_name = f'{base_name}.docx'

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, 'input.pdf')
        docx_path = os.path.join(tmp, 'output.docx')
        with open(pdf_path, 'wb') as handle:
            for chunk in uploaded_file.chunks():
                handle.write(chunk)
        converter = Converter(pdf_path)
        try:
            converter.convert(docx_path)
        finally:
            converter.close()
        with open(docx_path, 'rb') as handle:
            return handle.read(), output_name


def compress_image(uploaded_file, *, quality: int = 80, max_width: int | None = None) -> tuple[bytes, str, str]:
    """Nén ảnh — trả về (bytes, tên file, content_type)."""
    _validate_image(uploaded_file)
    quality = max(10, min(95, int(quality)))
    if max_width is not None:
        max_width = max(320, min(4096, int(max_width)))

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        img = img.convert('RGBA') if img.mode in ('RGBA', 'LA', 'P') else img.convert('RGB')
        if max_width and img.width > max_width:
            ratio = max_width / float(img.width)
            new_size = (max_width, max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'image.jpg'))[0]
        content_type = uploaded_file.content_type or 'image/jpeg'
        if content_type == 'image/png' or img.mode == 'RGBA':
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            return buffer.getvalue(), f'{base_name}-nen.png', 'image/png'

        buffer = io.BytesIO()
        rgb = img.convert('RGB') if img.mode != 'RGB' else img
        rgb.save(buffer, format='JPEG', quality=quality, optimize=True)
        return buffer.getvalue(), f'{base_name}-nen.jpg', 'image/jpeg'


def _get_background_removal_session():
    global _bg_session
    if _bg_session is None:
        from rembg import new_session
        _bg_session = new_session('u2net')
    return _bg_session


def warm_background_removal():
    """Tải sẵn mô hình AI — gọi sau deploy để tránh timeout lần đầu."""
    _get_background_removal_session()


def remove_image_background(uploaded_file) -> tuple[bytes, str]:
    """Xóa nền ảnh — trả về (bytes PNG, tên file gợi ý)."""
    from rembg import remove

    _validate_image(uploaded_file)
    uploaded_file.seek(0)
    output_bytes = remove(uploaded_file.read(), session=_get_background_removal_session())
    if not output_bytes:
        raise ValidationError('Không tách được chủ thể khỏi nền ảnh.')

    base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'image.png'))[0]
    return output_bytes, f'{base_name}-khong-nen.png'


def generate_qr_image(data: str, *, box_size: int = 10, border: int = 2) -> bytes:
    text = (data or '').strip()
    if not text:
        raise ValidationError('Vui lòng nhập nội dung mã QR.')
    if len(text) > 2000:
        raise ValidationError('Nội dung quá dài (tối đa 2000 ký tự).')

    box_size = max(4, min(20, int(box_size)))
    border = max(1, min(8, int(border)))

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
