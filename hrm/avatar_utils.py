import os
from io import BytesIO

from django.core.files.base import ContentFile

AVATAR_SIZE = 150


def prepare_avatar_image(upload, size: int = AVATAR_SIZE) -> ContentFile:
    """Cắt vuông giữa ảnh và resize về size×size (JPEG)."""
    from PIL import Image

    upload.seek(0)
    img = Image.open(upload)
    img.load()

    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        alpha = img.split()[-1] if img.mode in ('RGBA', 'LA') else None
        background.paste(img, mask=alpha)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((size, size), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=90, optimize=True)
    buffer.seek(0)

    stem = os.path.splitext(os.path.basename(getattr(upload, 'name', '') or 'avatar'))[0]
    safe_stem = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in stem) or 'avatar'
    return ContentFile(buffer.read(), name=f'{safe_stem}.jpg')
