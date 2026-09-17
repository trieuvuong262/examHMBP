"""Màu bộ phận trên KHSX / lộ trình — gắn slug tổ chuyền."""

from __future__ import annotations

import re

from django.db import transaction

from san_xuat.hub_models import SxTeamStageColor
from san_xuat.services.progress_template import TEAM_SLUGS

_HEX = re.compile(r'^#?[0-9a-fA-F]{6}$')
_SAFE_SLUG = re.compile(r'^[a-z0-9-]{1,30}$')

# Màu mặc định = ô bộ phận trên lưới lộ trình.
DEFAULT_TEAM_STAGE_COLORS: dict[str, str] = {
    'cat': '#ffd7b0',
    'inep': '#fecaca',
    'theu': '#fef08a',
    'may': '#bfdbfe',
    'ht': '#bbf7d0',
    'gh': '#f0cfe0',
}
_EXTRA_STAGE_COLORS: dict[str, str] = {
    'kho': '#a7f3d0',
}
_FALLBACK = '#94a3b8'


def normalize_hex_color(raw: str, default: str = _FALLBACK) -> str:
    text = (raw or '').strip()
    if not _HEX.match(text):
        return default
    if not text.startswith('#'):
        text = f'#{text}'
    return text.lower()


def mix_stage_ink(hex_color: str) -> str:
    color = normalize_hex_color(hex_color)
    red = max(18, int(int(color[1:3], 16) * 0.42))
    green = max(14, int(int(color[3:5], 16) * 0.36))
    blue = max(12, int(int(color[5:7], 16) * 0.32))
    return f'#{red:02x}{green:02x}{blue:02x}'


def mix_stage_soft(hex_color: str) -> str:
    color = normalize_hex_color(hex_color)
    red = min(255, int(int(color[1:3], 16) + (255 - int(color[1:3], 16)) * 0.78))
    green = min(255, int(int(color[3:5], 16) + (255 - int(color[3:5], 16)) * 0.78))
    blue = min(255, int(int(color[5:7], 16) + (255 - int(color[5:7], 16)) * 0.78))
    return f'#{red:02x}{green:02x}{blue:02x}'


def stage_color_spec(slug: str, fill: str = '') -> dict[str, str]:
    key = (slug or '').strip().lower()
    color = normalize_hex_color(
        fill
        or DEFAULT_TEAM_STAGE_COLORS.get(key)
        or _EXTRA_STAGE_COLORS.get(key)
        or _FALLBACK,
    )
    ink = mix_stage_ink(color)
    soft = mix_stage_soft(color)
    return {
        'slug': key,
        'color': color,
        'ink': ink,
        'soft': soft,
        'accent': ink,
    }


def team_stage_palette() -> dict[str, dict[str, str]]:
    """slug → {color, ink, soft, accent}. DB đè mặc định."""
    out: dict[str, dict[str, str]] = {}
    for slug, _gk, _mk, _label in TEAM_SLUGS:
        out[slug] = stage_color_spec(slug)
    for slug, fill in _EXTRA_STAGE_COLORS.items():
        out[slug] = stage_color_spec(slug, fill)
    try:
        for row in SxTeamStageColor.objects.all():
            slug = (row.team_slug or '').strip().lower()
            if not slug or not _SAFE_SLUG.match(slug):
                continue
            out[slug] = stage_color_spec(slug, row.color)
    except Exception:
        pass
    return out


def team_stage_color_css(extra_slugs: list[str] | None = None) -> str:
    palette = team_stage_palette()
    for slug in extra_slugs or []:
        key = (slug or '').strip().lower()
        if key and _SAFE_SLUG.match(key) and key not in palette:
            palette[key] = stage_color_spec(key)
    lines: list[str] = []
    for slug, spec in palette.items():
        if not _SAFE_SLUG.match(slug):
            continue
        lines.append(
            f".jp-stage-{slug}{{--st:{spec['accent']};--st-ink:{spec['ink']};"
            f"--st-fill:{spec['color']};--st-soft:{spec['soft']};}}"
        )
    return '\n'.join(lines)


@transaction.atomic
def save_team_stage_colors(payload: dict[str, str], *, saved_by=None) -> int:
    """Lưu {slug: #rrggbb}. Slug lạ / mã sai dùng mặc định. Trả số tổ đã ghi."""
    valid = {item[0] for item in TEAM_SLUGS}
    actor = saved_by if getattr(saved_by, 'is_authenticated', False) else None
    saved = 0
    for slug in valid:
        color = normalize_hex_color(
            (payload or {}).get(slug) or '',
            default=DEFAULT_TEAM_STAGE_COLORS.get(slug, _FALLBACK),
        )
        SxTeamStageColor.objects.update_or_create(
            team_slug=slug,
            defaults={'color': color, 'updated_by': actor},
        )
        saved += 1
    return saved
