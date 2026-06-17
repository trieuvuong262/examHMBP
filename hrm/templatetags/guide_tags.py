from django import template
from django.utils.safestring import mark_safe

from hrm.guide_editor import render_section_inner_default, section_display_title

register = template.Library()


@register.inclusion_tag('guide/_section_panel.html', takes_context=True)
def render_guide_section(context, section):
    section_id = section['id']
    overrides = context.get('section_overrides') or {}
    override = overrides.get(section_id) or {}
    inner = (override.get('body') or '').strip()
    if not inner:
        inner = render_section_inner_default(section_id, context['request'], context=context)
    title = section_display_title(section, overrides)
    icon = section.get('icon', 'bi-journal-text')
    return {
        'section_id': section_id,
        'title': title,
        'inner_html': mark_safe(inner) if inner else '',
        'is_active': section_id == 'bat-dau',
        'icon': icon,
        'has_inner': bool(inner),
    }
