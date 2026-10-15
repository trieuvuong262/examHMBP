"""Ghép ảnh mặt trước và mặt sau thành một ảnh 2 mặt (trái — phải)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

PANEL_W = 1000
PANEL_H = 1400
GAP = 36
PAD = 48
BG = (255, 255, 255)
DIVIDER = (226, 232, 240)


def compose_two_side_jpeg(front_path: Path, back_path: Path) -> bytes:
    front = _fit(_open_rgb(front_path))
    back = _fit(_open_rgb(back_path))
    row_h = max(front.height, back.height)
    width = PAD * 2 + front.width + GAP + back.width
    height = PAD * 2 + row_h
    canvas = Image.new('RGB', (width, height), BG)
    canvas.paste(front, (PAD, PAD + (row_h - front.height) // 2))
    canvas.paste(back, (PAD + front.width + GAP, PAD + (row_h - back.height) // 2))
    divider_x = PAD + front.width + GAP // 2
    ImageDraw.Draw(canvas).line([(divider_x, PAD), (divider_x, PAD + row_h - 1)], fill=DIVIDER, width=1)
    buf = BytesIO()
    canvas.save(buf, format='JPEG', quality=88, optimize=True)
    return buf.getvalue()


def _open_rgb(path: Path) -> Image.Image:
    try:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw) or raw
            image.load()
            return _flatten(image)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise OSError(f'Không đọc được ảnh {path.name}') from exc


def _flatten(image: Image.Image) -> Image.Image:
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        plate = Image.new('RGB', rgba.size, BG)
        plate.paste(rgba, mask=rgba.split()[-1])
        return plate
    if image.mode != 'RGB':
        return image.convert('RGB')
    return image.copy()


def _fit(image: Image.Image) -> Image.Image:
    image.thumbnail((PANEL_W, PANEL_H), Image.Resampling.LANCZOS)
    return image
