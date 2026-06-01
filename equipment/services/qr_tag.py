"""Tạo tem QR tài sản — branding JustPlay."""

import io
import os
import time
from datetime import datetime

import qrcode
from django.conf import settings
from django.core.files import File
from PIL import Image, ImageDraw, ImageFont


BRAND_COLOR = (220, 38, 38)  # --hm-primary #dc2626
TEXT_COLOR = (0, 0, 0)
BG_COLOR = (255, 255, 255)
TAG_WIDTH, TAG_HEIGHT = 650, 320
PADDING = 20
HEADER_HEIGHT = 60


def device_public_url(device_id) -> str:
    base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')
    return f'{base}/thiet-bi/qr/{device_id}/'


def _load_fonts():
    try:
        return (
            ImageFont.truetype('arialbd.ttf', 26),
            ImageFont.truetype('arialbd.ttf', 28),
            ImageFont.truetype('arial.ttf', 22),
            ImageFont.truetype('arial.ttf', 16),
        )
    except OSError:
        default = ImageFont.load_default()
        return default, default, default, default


def _format_handover_date(value) -> str:
    if not value:
        return 'N/A'
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            return value
    return value.strftime('%d/%m/%Y')


def generate_asset_tag(device) -> tuple[File, str]:
    """Vẽ tem QR PNG — trả về (File, filename)."""
    font_header, font_name, font_text, font_small = _load_fonts()
    img = Image.new('RGB', (TAG_WIDTH, TAG_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TAG_WIDTH - 1, TAG_HEIGHT - 1)], outline=BRAND_COLOR, width=6)
    draw.rectangle([(0, 0), (TAG_WIDTH, HEADER_HEIGHT)], fill=BRAND_COLOR)

    header_text = getattr(settings, 'EQUIPMENT_TAG_HEADER', 'JUSTPLAY — QUẢN LÝ THIẾT BỊ')
    try:
        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = draw.textsize(header_text, font=font_header)
    draw.text(
        ((TAG_WIDTH - text_w) / 2, (HEADER_HEIGHT - text_h) / 2 - 5),
        header_text,
        font=font_header,
        fill='white',
    )

    left_x = PADDING + 10
    current_y = HEADER_HEIGHT + PADDING + 5
    dept_label = device.usage_department_label

    draw.text((left_x, current_y), (device.name or '')[:25], font=font_name, fill=TEXT_COLOR)
    current_y += 50
    draw.text((left_x, current_y), f'BP: {dept_label}', font=font_text, fill=TEXT_COLOR)
    current_y += 35
    model = device.model_number or '--'
    draw.text((left_x, current_y), f'Model: {model}', font=font_text, fill=TEXT_COLOR)
    current_y += 35
    serial = device.serial_number or '--'
    draw.text((left_x, current_y), f'S/N: {serial}', font=font_text, fill=TEXT_COLOR)
    current_y += 35
    draw.text(
        (left_x, current_y),
        f'Ngày: {_format_handover_date(device.handover_date)}',
        font=font_text,
        fill=TEXT_COLOR,
    )
    draw.text((left_x, TAG_HEIGHT - 30), f'ID: {device.id}', font=font_small, fill='gray')

    qr_data = device_public_url(device.id)
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=BRAND_COLOR, back_color='white').resize((220, 220))
    img.paste(qr_img, (TAG_WIDTH - 220 - PADDING, HEADER_HEIGHT + 20))

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    filename = f'AssetTag_{device.id}_{int(time.time())}.png'
    return File(buffer, name=filename), filename


def should_redraw_tag(update_fields) -> bool:
    if not update_fields:
        return True
    tag_fields = {'name', 'usage_department', 'usage_department_text', 'model_number', 'serial_number', 'handover_date', 'qr_code'}
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
