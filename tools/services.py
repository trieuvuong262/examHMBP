import io
import os
import shutil
import subprocess
import tempfile
import threading

import qrcode
from django.core.exceptions import ValidationError
from PIL import Image, ImageDraw, ImageFont


PDF_MAX_BYTES = 10 * 1024 * 1024
OFFICE_MAX_BYTES = 15 * 1024 * 1024
IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

OFFICE_WORD_EXTENSIONS = {'.doc', '.docx', '.odt', '.rtf'}
OFFICE_EXCEL_EXTENSIONS = {'.xls', '.xlsx', '.ods', '.csv'}
OFFICE_TO_PDF_EXTENSIONS = OFFICE_WORD_EXTENSIONS | OFFICE_EXCEL_EXTENSIONS

OUTPUT_IMAGE_FORMATS = {
    'jpeg': ('JPEG', 'image/jpeg', '.jpg'),
    'jpg': ('JPEG', 'image/jpeg', '.jpg'),
    'png': ('PNG', 'image/png', '.png'),
    'webp': ('WEBP', 'image/webp', '.webp'),
}

WATERMARK_POSITIONS = {
    'center',
    'bottom-right',
    'bottom-left',
    'top-right',
    'top-left',
    'tile',
}

_FONT_CANDIDATES = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans.ttf',
    'C:/Windows/Fonts/arial.ttf',
    'C:/Windows/Fonts/segoeui.ttf',
)

_bg_session = None
_bg_lock = threading.Lock()
_bg_warming = False


class BackgroundRemovalNotReady(Exception):
    """Mô hình AI đang tải — client nên thử lại."""


def _validate_pdf(uploaded_file):
    if uploaded_file.size > PDF_MAX_BYTES:
        raise ValidationError('File không hợp lệ.')
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
        raise ValidationError('File không hợp lệ.')
    if uploaded_file.content_type and uploaded_file.content_type not in IMAGE_TYPES:
        raise ValidationError('File không hợp lệ.')


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


def is_background_removal_ready() -> bool:
    return _bg_session is not None


def _get_background_removal_session(*, wait: bool = True):
    global _bg_session, _bg_warming
    if _bg_session is not None:
        return _bg_session
    if _bg_warming and not wait:
        raise BackgroundRemovalNotReady()

    with _bg_lock:
        if _bg_session is not None:
            return _bg_session
        if _bg_warming and not wait:
            raise BackgroundRemovalNotReady()
        _bg_warming = True
        try:
            from rembg import new_session
            _bg_session = new_session('u2net')
        finally:
            _bg_warming = False
    return _bg_session


def warm_background_removal():
    """Tải sẵn mô hình AI — gọi sau deploy / khi worker khởi động."""
    _get_background_removal_session(wait=True)


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


def _validate_office_for_pdf(uploaded_file):
    if uploaded_file.size > OFFICE_MAX_BYTES:
        raise ValidationError('File không hợp lệ.')
    name = (uploaded_file.name or '').lower()
    ext = os.path.splitext(name)[1]
    if ext not in OFFICE_TO_PDF_EXTENSIONS:
        raise ValidationError('File không hợp lệ.')


def _libreoffice_binary() -> str | None:
    for candidate in ('soffice', 'libreoffice'):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _run_libreoffice_convert(input_path: str, output_dir: str) -> str:
    binary = _libreoffice_binary()
    if not binary:
        raise ValidationError(
            'Server chưa cài LibreOffice. Liên hệ IT để bật công cụ Word/Excel → PDF.'
        )

    env = os.environ.copy()
    env.setdefault('HOME', '/tmp')
    result = subprocess.run(
        [
            binary,
            '--headless',
            '--norestore',
            '--nolockcheck',
            '--nodefault',
            '--nofirststartwizard',
            '--convert-to',
            'pdf',
            '--outdir',
            output_dir,
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip()
        raise ValidationError(
            'Không chuyển được sang PDF.'
            + (f' ({detail[:200]})' if detail else '')
        )

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    pdf_path = os.path.join(output_dir, f'{base_name}.pdf')
    if not os.path.isfile(pdf_path):
        raise ValidationError('LibreOffice không tạo được file PDF.')
    return pdf_path


def convert_office_to_pdf(uploaded_file) -> tuple[bytes, str]:
    """Chuyển Word / Excel sang PDF."""
    _validate_office_for_pdf(uploaded_file)
    base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'document'))[0]
    ext = os.path.splitext(uploaded_file.name or '')[1].lower() or '.docx'
    output_name = f'{base_name}.pdf'

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, f'input{ext}')
        with open(input_path, 'wb') as handle:
            for chunk in uploaded_file.chunks():
                handle.write(chunk)
        pdf_path = _run_libreoffice_convert(input_path, tmp)
        with open(pdf_path, 'rb') as handle:
            data = handle.read()
        if not data.startswith(b'%PDF'):
            raise ValidationError('File kết quả không phải PDF hợp lệ.')
        return data, output_name


def convert_office_path_to_pdf(file_path: str | os.PathLike) -> tuple[bytes, str]:
    """Chuyển file Word / Excel trên đĩa sang PDF (xem trước NAS, v.v.)."""
    path = os.path.abspath(str(file_path))
    if not os.path.isfile(path):
        raise ValidationError('File không tồn tại.')
    if os.path.getsize(path) > OFFICE_MAX_BYTES:
        raise ValidationError('File không hợp lệ.')
    ext = os.path.splitext(path)[1].lower()
    if ext not in OFFICE_TO_PDF_EXTENSIONS:
        raise ValidationError('File không hợp lệ.')
    base_name = os.path.splitext(os.path.basename(path))[0]
    output_name = f'{base_name}.pdf'

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, f'input{ext}')
        shutil.copyfile(path, input_path)
        pdf_path = _run_libreoffice_convert(input_path, tmp)
        with open(pdf_path, 'rb') as handle:
            data = handle.read()
        if not data.startswith(b'%PDF'):
            raise ValidationError('File kết quả không phải PDF hợp lệ.')
        return data, output_name


def office_preview_available() -> bool:
    return _libreoffice_binary() is not None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _watermark_coords(
    base_size: tuple[int, int],
    mark_size: tuple[int, int],
    position: str,
    *,
    margin: int,
) -> tuple[int, int]:
    width, height = base_size
    mark_w, mark_h = mark_size
    if position == 'center':
        return ((width - mark_w) // 2, (height - mark_h) // 2)
    if position == 'bottom-left':
        return (margin, height - mark_h - margin)
    if position == 'top-right':
        return (width - mark_w - margin, margin)
    if position == 'top-left':
        return (margin, margin)
    if position == 'tile':
        return (margin, margin)
    return (width - mark_w - margin, height - mark_h - margin)


def apply_image_watermark(
    uploaded_file,
    *,
    text: str = 'JustPlay',
    position: str = 'bottom-right',
    opacity: int = 35,
    watermark_file=None,
) -> tuple[bytes, str, str]:
    """Đóng watermark chữ hoặc ảnh — trả về (bytes, tên file, content_type)."""
    _validate_image(uploaded_file)
    position = position if position in WATERMARK_POSITIONS else 'bottom-right'
    opacity = max(5, min(90, int(opacity)))
    alpha = int(255 * (opacity / 100.0))

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as base:
        base = base.convert('RGBA')
        overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
        margin = max(12, int(min(base.size) * 0.02))

        if watermark_file:
            with Image.open(watermark_file) as mark_img:
                mark = mark_img.convert('RGBA')
                target_w = max(48, int(base.width * 0.22))
                ratio = target_w / float(mark.width)
                target_h = max(1, int(mark.height * ratio))
                mark = mark.resize((target_w, target_h), Image.Resampling.LANCZOS)
                if position == 'tile':
                    step_x = max(target_w + margin, int(target_w * 1.4))
                    step_y = max(target_h + margin, int(target_h * 1.4))
                    for y in range(0, base.height, step_y):
                        for x in range(0, base.width, step_x):
                            overlay.alpha_composite(mark, (x, y))
                else:
                    x, y = _watermark_coords(base.size, mark.size, position, margin=margin)
                    overlay.alpha_composite(mark, (x, y))
        else:
            label = (text or 'JustPlay').strip()[:80] or 'JustPlay'
            font_size = max(16, int(min(base.width, base.height) * 0.05))
            font = _load_font(font_size)
            draw = ImageDraw.Draw(overlay)
            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            if position == 'tile':
                step_x = text_w + margin * 3
                step_y = text_h + margin * 3
                for y in range(0, base.height, step_y):
                    for x in range(0, base.width, step_x):
                        draw.text((x, y), label, font=font, fill=(255, 255, 255, alpha))
            else:
                x, y = _watermark_coords(
                    base.size,
                    (text_w, text_h),
                    position,
                    margin=margin,
                )
                draw.text((x, y), label, font=font, fill=(255, 255, 255, alpha))

        result = Image.alpha_composite(base, overlay)
        base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'image.png'))[0]
        buffer = io.BytesIO()
        result.save(buffer, format='PNG', optimize=True)
        return buffer.getvalue(), f'{base_name}-watermark.png', 'image/png'


def convert_image_format(
    uploaded_file,
    target_format: str,
    *,
    quality: int = 85,
) -> tuple[bytes, str, str]:
    """Đổi định dạng ảnh — JPEG / PNG / WebP."""
    _validate_image(uploaded_file)
    fmt_key = (target_format or 'png').strip().lower()
    if fmt_key not in OUTPUT_IMAGE_FORMATS:
        raise ValidationError('Chọn định dạng đích: JPEG, PNG hoặc WebP.')

    pil_format, content_type, ext = OUTPUT_IMAGE_FORMATS[fmt_key]
    quality = max(50, min(95, int(quality)))

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        base_name = os.path.splitext(os.path.basename(uploaded_file.name or 'image'))[0]
        buffer = io.BytesIO()

        if pil_format == 'JPEG':
            rgb = img.convert('RGB')
            rgb.save(buffer, format='JPEG', quality=quality, optimize=True)
        elif pil_format == 'PNG':
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            img.save(buffer, format='PNG', optimize=True)
        else:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            img.save(buffer, format='WEBP', quality=quality, method=4)

        return buffer.getvalue(), f'{base_name}{ext}', content_type


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
