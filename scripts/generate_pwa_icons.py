"""
Tạo icon PWA / shortcut từ static/images/logo/logo.png (không ghi đè logo.png).

Chạy: python scripts/generate_pwa_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "static" / "images" / "logo"
SOURCE = LOGO_DIR / "logo.png"

# Kích thước chuẩn (W3C / Apple / Google)
DERIVED = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def load_source() -> Image.Image:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source: {SOURCE}")
    img = Image.open(SOURCE)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def fit_square(img: Image.Image, size: int) -> Image.Image:
    """Scale giữ tỉ lệ, căn giữa trên nền trong suốt."""
    img = img.copy()
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    canvas.paste(img, (x, y), img)
    return canvas


def fit_maskable(img: Image.Image, size: int = 512) -> Image.Image:
    """
    Icon maskable Android: nội dung trong vùng an toàn ~80% (Google adaptive icon).
    """
    safe = int(size * 0.8)
    scaled = img.copy()
    scaled.thumbnail((safe, safe), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - scaled.width) // 2
    y = (size - scaled.height) // 2
    canvas.paste(scaled, (x, y), scaled)
    return canvas


def save_png(image: Image.Image, path: Path) -> None:
    image.save(path, format="PNG", optimize=True)
    print(f"  {path.name}  {image.width}x{image.height}  ({path.stat().st_size} bytes)")


def main() -> None:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    source = load_source()
    print(f"Source: {SOURCE} ({source.width}x{source.height})")
    print("Writing derived icons:")

    for filename, size in DERIVED.items():
        save_png(fit_square(source, size), LOGO_DIR / filename)

    save_png(fit_maskable(source, 512), LOGO_DIR / "icon-512-maskable.png")
    print("Done (logo.png unchanged).")


if __name__ == "__main__":
    main()
