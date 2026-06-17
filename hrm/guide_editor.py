"""Soạn thảo hướng dẫn theo từng mục — admin."""

from __future__ import annotations

import logging

from django.template.loader import render_to_string

from hrm.guide_sections import GUIDE_SECTIONS, get_section_by_id

logger = logging.getLogger(__name__)


def all_guide_sections_for_admin() -> list[dict]:
    return sorted(GUIDE_SECTIONS, key=lambda s: s['order'])


def normalize_section_overrides(raw: dict | None) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, val in raw.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(val, str):
            body = val.strip()
            if body:
                out[key] = {'body': body}
            continue
        if isinstance(val, dict):
            body = (val.get('body') or '').strip()
            title = (val.get('title') or '').strip()
            entry = {}
            if body:
                entry['body'] = body
            if title:
                entry['title'] = title
            if entry:
                out[key] = entry
    return out


def section_display_title(section: dict, overrides: dict) -> str:
    custom = overrides.get(section['id'], {})
    return custom.get('title') or section.get('toc_display') or section['toc']


def section_has_override(section_id: str, overrides: dict) -> bool:
    return bool((overrides.get(section_id) or {}).get('body'))


def _as_template_context(context) -> dict:
    if hasattr(context, 'flatten'):
        return context.flatten()
    if isinstance(context, dict):
        return context
    return dict(context)


def render_section_inner_default(section_id: str, request, *, context) -> str:
    """HTML bên trong .accordion-body — mặc định từ template partial."""
    template = f'guide/inner/{section_id}.html'
    try:
        return render_to_string(
            template,
            _as_template_context(context),
            request=request,
        ).strip()
    except Exception:
        logger.exception('guide inner template failed: %s', section_id)
        return ''


def get_section_edit_initial(section_id: str, guide, request, *, context: dict) -> dict:
    section = get_section_by_id(section_id)
    if not section:
        return {}
    overrides = normalize_section_overrides(guide.section_overrides)
    custom = overrides.get(section_id, {})
    body = custom.get('body') or render_section_inner_default(section_id, request, context=context)
    return {
        'section_id': section_id,
        'title': custom.get('title') or section['toc'],
        'body': body,
        'is_custom': section_has_override(section_id, overrides),
    }


def save_section_override(guide, section_id: str, *, title: str, body: str) -> None:
    overrides = dict(guide.section_overrides or {})
    title = (title or '').strip()
    body = (body or '').strip()
    section = get_section_by_id(section_id)
    default_title = section['toc'] if section else ''

    if not body:
        overrides.pop(section_id, None)
    else:
        entry = {'body': body}
        if title and title != default_title:
            entry['title'] = title
        overrides[section_id] = entry

    guide.section_overrides = overrides
    guide.save(update_fields=['section_overrides', 'updated_at'])


def clear_section_override(guide, section_id: str) -> None:
    overrides = dict(guide.section_overrides or {})
    overrides.pop(section_id, None)
    guide.section_overrides = overrides
    guide.save(update_fields=['section_overrides', 'updated_at'])
