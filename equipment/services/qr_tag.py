"""Tạo tem QR tài sản — branding JustPlay."""

import io
import os
import time
from datetime import datetime
from pathlib import Path

import qrcode
from django.conf import settings
from django.core.files import File
from PIL import Image, ImageDraw, ImageFont


BRAND_PRIMARY = (220, 38, 38)
BRAND_DARK = (153, 27, 27)
TEXT_DARK = (17, 24, 39)
TEXT_MUTED = (107, 114, 128)
BG_WHITE = (255, 255, 255)
ACCENT_LIGHT = (254, 242, 242)

TAG_WIDTH, TAG_HEIGHT = 760, 400
PADDING = 28
HEADER_HEIGHT = 72
QR_SIZE = 200


def device_public_url(device_id) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')
    return f'{base}/thiet-bi/qr/{device_id}/'


def _font_search_paths(*filenames: str):
    base = Path(getattr(settings, 'BASE_DIR', Path.cwd()))
    dirs = [
        base / 'static' / 'fonts',
        Path('/usr/share/fonts/truetype/noto'),
        Path('/usr/share/fonts/truetype/dejavu'),
        Path('C:/Windows/Fonts'),
    ]
    for directory in dirs:
        for name in filenames:
            candidate = directory / name
            if candidate.is_file():
                yield candidate


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if bold:
        names = ('NotoSans-Bold.ttf', 'DejaVuSans-Bold.ttf', 'arialbd.ttf', 'segoeuib.ttf')
    else:
        names = ('NotoSans-Regular.ttf', 'DejaVuSans.ttf', 'arial.ttf', 'segoeui.ttf')
    for path in _font_search_paths(*names):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_fonts():
    return (
        _load_font(22, bold=True),
        _load_font(28, bold=True),
        _load_font(19),
        _load_font(15),
        _load_font(13, bold=True),
    )


def _format_handover_date(value) -> str:
    if not value:
        return '—'
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            return value
    return value.strftime('%d/%m/%Y')


def _draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def generate_asset_tag(device) -> tuple[File, str]:
    """Vẽ tem QR PNG — trả về (File, filename)."""
    font_brand, font_name, font_text, font_small, font_caps = _load_fonts()
    img = Image.new('RGB', (TAG_WIDTH, TAG_HEIGHT), BG_WHITE)
    draw = ImageDraw.Draw(img)

    _draw_rounded_rect(draw, (8, 8, TAG_WIDTH - 8, TAG_HEIGHT - 8), radius=16, outline=BRAND_PRIMARY, width=3)

    for y in range(HEADER_HEIGHT):
        ratio = y / max(HEADER_HEIGHT - 1, 1)
        r = int(BRAND_DARK[0] + (BRAND_PRIMARY[0] - BRAND_DARK[0]) * ratio)
        g = int(BRAND_DARK[1] + (BRAND_PRIMARY[1] - BRAND_DARK[1]) * ratio)
        b = int(BRAND_DARK[2] + (BRAND_PRIMARY[2] - BRAND_DARK[2]) * ratio)
        draw.line([(16, 8 + y), (TAG_WIDTH - 16, 8 + y)], fill=(r, g, b))

    header_text = getattr(settings, 'EQUIPMENT_TAG_HEADER', 'JUSTPLAY')
    sub_header = 'QUẢN LÝ THIẾT BỊ · QUÉT BÁO HỎNG'
    draw.text((PADDING + 4, 18), header_text, font=font_brand, fill='white')
    draw.text((PADDING + 4, 44), sub_header, font=font_caps, fill=(254, 226, 226))

    left_x = PADDING + 4
    content_top = HEADER_HEIGHT + 24
    name = (device.name or 'Thiết bị')[:28]
    draw.text((left_x, content_top), name, font=font_name, fill=TEXT_DARK)

    dept_label = device.usage_department_label
    user_label = device.assigned_user_label if hasattr(device, 'assigned_user_label') else (device.assigned_user_text or '')
    current_y = content_top + 44

    info_lines = [
        ('Phòng ban', dept_label),
        ('Người dùng', user_label if user_label and user_label != '—' else '—'),
        ('Model', device.model_number or '—'),
        ('Serial', (device.serial_number or '—')[:32]),
        ('Bàn giao', _format_handover_date(device.handover_date)),
    ]
    for label, value in info_lines:
        draw.text((left_x, current_y), label.upper(), font=font_caps, fill=TEXT_MUTED)
        draw.text((left_x + 108, current_y - 1), str(value)[:36], font=font_text, fill=TEXT_DARK)
        current_y += 34

    qr_x = TAG_WIDTH - QR_SIZE - PADDING - 12
    qr_y = HEADER_HEIGHT + 28
    _draw_rounded_rect(
        draw,
        (qr_x - 14, qr_y - 14, qr_x + QR_SIZE + 14, qr_y + QR_SIZE + 14),
        radius=12,
        fill=ACCENT_LIGHT,
        outline=BRAND_PRIMARY,
        width=2,
    )

    qr_data = device_public_url(device.id)
    qr = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=BRAND_PRIMARY, back_color='white').convert('RGB')
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)
    img.paste(qr_img, (qr_x, qr_y))

    scan_hint = 'Quét mã → Báo hỏng IT'
    hint_bbox = draw.textbbox((0, 0), scan_hint, font=font_small)
    hint_w = hint_bbox[2] - hint_bbox[0]
    draw.text(
        (qr_x + (QR_SIZE - hint_w) // 2, qr_y + QR_SIZE + 18),
        scan_hint,
        font=font_small,
        fill=BRAND_PRIMARY,
    )

    device_id_short = str(device.id).split('-')[0].upper()
    draw.text((left_x, TAG_HEIGHT - 36), f'ID {device_id_short}', font=font_small, fill=TEXT_MUTED)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    filename = f'AssetTag_{device.id}_{int(time.time())}.png'
    return File(buffer, name=filename), filename


def should_redraw_tag(update_fields) -> bool:
    if not update_fields:
        return True
    tag_fields = {
        'name', 'usage_department', 'usage_department_text', 'model_number',
        'serial_number', 'handover_date', 'assigned_user', 'assigned_user_text', 'qr_code',
    }
    return bool(set(update_fields).intersection(tag_fields))


def remove_old_qr_file(device):
    if device.pk:
        try:
            from equipment.models import Device
            old = Device.objects.get(pk=device.pk)
            if old.qr_code and os.path.isfile(old.qr_code.path):
                os.remove(old.qr_code.path)
        except Exception:
            pass
