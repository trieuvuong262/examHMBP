"""Tạo tem QR tài sản — vuông, tông đen, không bo góc."""

import io
import os
import time
from datetime import datetime
from pathlib import Path

import qrcode
from django.conf import settings
from django.core.files import File
from PIL import Image, ImageDraw, ImageFont

BLACK = (0, 0, 0)
BLACK_SOFT = (30, 30, 30)
TEXT_MUTED = (100, 100, 100)
BG_WHITE = (255, 255, 255)

TAG_SIZE = 480
PADDING = 22
HEADER_HEIGHT = 52
QR_SIZE = 164
BTN_W = 300
BTN_H = 40


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


def _text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_centered_text(draw, y, text, font, fill, width=TAG_SIZE):
    tw = _text_width(draw, text, font)
    draw.text(((width - tw) // 2, y), text, font=font, fill=fill)


def generate_asset_tag(device) -> tuple[File, str]:
    """Vẽ tem QR vuông PNG — góc vuông, nút đen «Quét để báo hỏng»."""
    font_brand = _load_font(17, bold=True)
    font_sub = _load_font(11, bold=True)
    font_name = _load_font(21, bold=True)
    font_row = _load_font(14)
    font_label = _load_font(11, bold=True)
    font_btn = _load_font(13, bold=True)
    font_id = _load_font(11)

    img = Image.new('RGB', (TAG_SIZE, TAG_SIZE), BG_WHITE)
    draw = ImageDraw.Draw(img)

    draw.rectangle((4, 4, TAG_SIZE - 4, TAG_SIZE - 4), outline=BLACK, width=3)
    draw.rectangle((8, 8, TAG_SIZE - 8, 8 + HEADER_HEIGHT), fill=BLACK)

    header_text = getattr(settings, 'EQUIPMENT_TAG_HEADER', 'JUSTPLAY')
    _draw_centered_text(draw, 16, header_text, font_brand, 'white')
    _draw_centered_text(draw, 34, 'QUẢN LÝ THIẾT BỊ', font_sub, (190, 190, 190))

    y = 8 + HEADER_HEIGHT + 14
    name = (device.name or 'Thiết bị')[:26]
    _draw_centered_text(draw, y, name, font_name, BLACK)
    y += 28

    dept_label = device.usage_department_label
    user_label = device.assigned_user_label if hasattr(device, 'assigned_user_label') else (device.assigned_user_text or '')
    rows = [
        ('PHÒNG BAN', dept_label),
        ('NGƯỜI DÙNG', user_label if user_label and user_label != '—' else '—'),
        ('MODEL', device.model_number or '—'),
        ('SERIAL', (device.serial_number or '—')[:28]),
    ]
    label_w = 92
    left = PADDING + 6
    for label, value in rows:
        draw.text((left, y), label, font=font_label, fill=TEXT_MUTED)
        draw.text((left + label_w, y), str(value)[:32], font=font_row, fill=BLACK_SOFT)
        y += 21

    qr_y = y + 6
    qr_x = (TAG_SIZE - QR_SIZE) // 2
    draw.rectangle(
        (qr_x - 8, qr_y - 8, qr_x + QR_SIZE + 8, qr_y + QR_SIZE + 8),
        outline=BLACK,
        width=2,
    )

    qr_data = device_public_url(device.id)
    qr = qrcode.QRCode(box_size=6, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=BLACK, back_color='white').convert('RGB')
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.Resampling.LANCZOS)
    img.paste(qr_img, (qr_x, qr_y))

    btn_x = (TAG_SIZE - BTN_W) // 2
    btn_y = qr_y + QR_SIZE + 12
    draw.rectangle((btn_x, btn_y, btn_x + BTN_W, btn_y + BTN_H), fill=BLACK)
    _draw_centered_text(draw, btn_y + 11, 'Quét để báo hỏng', font_btn, 'white')

    device_id_short = str(device.id).split('-')[0].upper()
    id_text = f'ID {device_id_short}'
    id_w = _text_width(draw, id_text, font_id)
    draw.text((TAG_SIZE - PADDING - id_w, TAG_SIZE - PADDING - 12), id_text, font=font_id, fill=TEXT_MUTED)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    buffer.seek(0)
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
