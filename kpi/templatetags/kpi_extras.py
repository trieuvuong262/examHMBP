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
    """User ID của HOD quản lý trực tiếp (Profile.subordinates M2M)."""
    hod_profile = user.my_hod_managers.first()
    return hod_profile.user_id if hod_profile else ''


@register.filter
def profile_name(profile):
    if not profile:
        return ''
    if profile.full_name:
        return profile.full_name
    return getattr(profile.user, 'username', '')


@register.filter
def profile_field(user, field_name):
    profile = get_profile(user)
    if not profile:
        return ''
    value = getattr(profile, field_name, '')
    if callable(value):
        return ''
    return value or ''


@register.filter
def get_attr(obj, attr_name):
    """Lấy attribute động. VD: item|get_attr:'q1_self'"""
    if hasattr(obj, attr_name):
        return super(obj.__class__, obj).__getattribute__(attr_name)
    return None


@register.filter(name='getattr')
def getattr_filter(obj, attr_name):
    """Alias template |getattr — không đặt tên hàm Python là getattr."""
    return get_attr(obj, attr_name)


@register.filter
def divide(value, arg):
    """Filter chia chỉ tiêu cho Quý/Bán niên, làm tròn 2 chữ số"""
    try:
        return round(float(value) / float(arg), 2)
    except (ValueError, ZeroDivisionError, TypeError):
        return value
