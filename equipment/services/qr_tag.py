"""Tạo tem QR tài sản — hình chữ nhật, tông đen, không bo góc."""

import io
import os
import time
from pathlib import Path

import qrcode
from django.conf import settings
from django.core.files import File
from PIL import Image, ImageDraw, ImageFont

BLACK = (0, 0, 0)
BLACK_SOFT = (30, 30, 30)
TEXT_MUTED = (100, 100, 100)
BG_WHITE = (255, 255, 255)
LINE_GRAY = (220, 220, 220)

TAG_W = 720
TAG_H = 260
BORDER = 3
INNER = 8
HEADER_H = 46
RIGHT_W = 210
QR_SIZE = 168


def device_public_url(device_code: str) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')
    return f'{base}/thiet-bi/qr/{device_code}/'


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


def _text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _text_height(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def generate_asset_tag(device) -> tuple[File, str]:
    """Tem ngang: trái = thông tin thiết bị, phải = mã QR."""
    font_brand = _load_font(16, bold=True)
    font_name = _load_font(20, bold=True)
    font_row = _load_font(13)
    font_label = _load_font(10, bold=True)

    img = Image.new('RGB', (TAG_W, TAG_H), BG_WHITE)
    draw = ImageDraw.Draw(img)

    draw.rectangle((BORDER, BORDER, TAG_W - BORDER, TAG_H - BORDER), outline=BLACK, width=BORDER)
    draw.rectangle((INNER, INNER, TAG_W - INNER, INNER + HEADER_H), fill=BLACK)

    header_text = getattr(settings, 'EQUIPMENT_TAG_HEADER', 'JUSTPLAY')
    header_y = INNER + (HEADER_H - _text_height(draw, header_text, font_brand)) // 2
    draw.text((INNER + 12, header_y), header_text, font=font_brand, fill='white')

    body_top = INNER + HEADER_H + 10
    body_bottom = TAG_H - INNER - 8
    split_x = TAG_W - INNER - RIGHT_W

    draw.line((split_x, body_top, split_x, body_bottom), fill=LINE_GRAY, width=1)

    left_x = INNER + 14
    label_w = 88
    row_h = 19
    y = body_top + 4

    name = (device.name or 'Thiết bị')[:36]
    draw.text((left_x, y), name, font=font_name, fill=BLACK)
    y += _text_height(draw, name, font_name) + 6

    category = device.get_category_display() if hasattr(device, 'get_category_display') else ''
    if category:
        draw.text((left_x, y), f'Loại: {category[:40]}', font=font_row, fill=BLACK_SOFT)
        y += 20

    device_code = (getattr(device, 'device_code', None) or '—')[:32]
    dept_label = device.usage_department_label if hasattr(device, 'usage_department_label') else '—'
    user_label = device.assigned_user_label if hasattr(device, 'assigned_user_label') else (device.assigned_user_text or '—')
    if user_label == '—':
        user_label = device.assigned_user_text or '—'

    handover_label = '—'
    if getattr(device, 'handover_date', None):
        handover_label = device.handover_date.strftime('%d/%m/%Y')

    rows = [
        ('MÃ THIẾT BỊ', device_code),
        ('PHÒNG BAN', dept_label),
        ('NGƯỜI DÙNG', user_label),
        ('MODEL', device.model_number or '—'),
        ('SERIAL', (device.serial_number or '—')[:32]),
        ('BÀN GIAO', handover_label),
    ]
    for label, value in rows:
        if y + row_h > body_bottom - 8:
            break
        draw.text((left_x, y), label, font=font_label, fill=TEXT_MUTED)
        draw.text((left_x + label_w, y), str(value)[:38], font=font_row, fill=BLACK_SOFT)
        y += row_h

    qr_x = split_x + (RIGHT_W - QR_SIZE) // 2
    qr_y = body_top + 16
    draw.rectangle(
        (qr_x - 6, qr_y - 6, qr_x + QR_SIZE + 6, qr_y + QR_SIZE + 6),
        outline=BLACK,
        width=2,
    )

    qr_data = device_public_url(device_code if device_code != '—' else str(device.id))
    qr = qrcode.QRCode(box_size=6, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=BLACK, back_color='white').convert('RGB')
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)
    img.paste(qr_img, (qr_x, qr_y))

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
    code_slug = device_code.replace('/', '-') if device_code != '—' else str(device.id)
    filename = f'AssetTag_{code_slug}_{int(time.time())}.png'
    return File(buffer, name=filename), filename


def should_redraw_tag(update_fields) -> bool:
    if not update_fields:
        return True
    tag_fields = {
        'device_code', 'name', 'category', 'usage_department', 'usage_department_text', 'model_number',
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
