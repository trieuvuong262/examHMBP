import re

from django import template
from django.utils import timezone

from thiet_ke_sp.permissions import avatar_tone_for, display_name, user_avatar_url, user_initial

register = template.Library()

_HEX = re.compile(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')


@register.filter
def uname(user):
    return display_name(user) or '-'


@register.filter
def owner_names(dossier):
    names = []
    for person in (getattr(dossier, 'owner', None), getattr(dossier, 'co_owner', None)):
        name = display_name(person)
        if name and name not in names:
            names.append(name)
    return ', '.join(names) if names else '-'


@register.filter
def avatar_url(user):
    """Ảnh đại diện trên hồ sơ nhân sự. Rỗng nếu chưa có ảnh."""
    return user_avatar_url(user)


@register.filter
def initial(user):
    return user_initial(user)


@register.filter
def avatar_tone(value):
    return avatar_tone_for(value)


@register.filter
def cw_swatch(color_codes):
    colors = _HEX.findall(color_codes or '')
    if not colors:
        return 'linear-gradient(135deg, #404040, #a3a3a3)'
    if len(colors) == 1:
        return colors[0]
    return f'linear-gradient(135deg, {colors[0]} 55%, {colors[1]} 55%)'


@register.filter
def due_label(value):
    if not value:
        return '-'
    return timezone.localtime(value).strftime('%H:%M %d/%m/%Y')


@register.filter
def due_short(value):
    if not value:
        return '-'
    return timezone.localtime(value).strftime('%d/%m · %H:%M')


@register.filter
def due_remaining(value):
    if not value:
        return ''
    delta = value - timezone.now()
    seconds = delta.total_seconds()
    if seconds < 0:
        return f'Trễ {days_late(value)} ngày'
    hours = int(seconds // 3600)
    if hours < 24:
        return f'Còn {max(hours, 1)} giờ'
    return f'Còn {hours // 24} ngày'


@register.filter
def due_input(value):
    if not value:
        return ''
    return timezone.localtime(value).strftime('%Y-%m-%dT%H:%M')


@register.filter
def days_late(value):
    if not value or value >= timezone.now():
        return 0
    return max((timezone.localdate() - timezone.localtime(value).date()).days, 1)


@register.simple_tag
def size_spec_groups(text, editable=False):
    from thiet_ke_sp.services.size_spec import size_groups

    return size_groups(text or '', selected_only=not editable)


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
