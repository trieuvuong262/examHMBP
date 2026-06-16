from django import template

register = template.Library()


@register.filter
def guide_get(d: dict, key: str):
    if not d:
        return ''
    return d.get(key, '')


@register.simple_tag
def guide_section_title(section, overrides):
    custom = (overrides or {}).get(section['id'], {})
    return custom.get('title') or section['toc']
