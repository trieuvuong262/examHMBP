from django import template
from hrm.permissions import get_profile

register = template.Library()

@register.filter
def display_name(user):
    profile = get_profile(user)
    if profile and profile.full_name:
        return profile.full_name
    return getattr(user, 'username', '')

@register.filter
def direct_manager_id(user):
    profile = get_profile(user)
    return profile.direct_manager_id if profile and profile.direct_manager_id else ''

@register.filter
def profile_field(user, field_name):
    profile = get_profile(user)
    if not profile:
        return ''
    return getattr(profile, field_name, '') or ''

@register.filter
def getattr(obj, attr_name):
    """Filter tùy chỉnh để lấy attribute động. VD: item|getattr:'q1_self'"""
    if hasattr(obj, attr_name):
        return super(obj.__class__, obj).__getattribute__(attr_name)
    return None

@register.filter
def divide(value, arg):
    """Filter chia chỉ tiêu cho Quý/Bán niên, làm tròn 2 chữ số"""
    try:
        return round(float(value) / float(arg), 2)
    except (ValueError, ZeroDivisionError, TypeError):
        return value