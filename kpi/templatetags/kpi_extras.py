from django import template
from hrm.permissions import get_profile

from kpi.services.inline_images import actual_html_for_edit, render_actual_html

register = template.Library()


@register.filter
def display_name(user):
    profile = get_profile(user)
    if profile and profile.full_name:
        return profile.full_name
    return getattr(user, 'username', '')


@register.filter
def kpi_actual(value):
    """Hiển thị Đánh giá thực tế (text hoặc HTML có ảnh)."""
    return render_actual_html(value)


@register.filter
def kpi_actual_edit(value):
    """Nội dung khởi tạo contenteditable."""
    return actual_html_for_edit(value)


@register.filter
def direct_manager_id(user):
    """User ID của QL gần nhất theo Nhân sự (Profile.subordinates / kiêm nhiệm)."""
    from hrm.permissions import primary_direct_manager
    mgr = primary_direct_manager(user)
    return mgr.pk if mgr else ''


@register.filter
def hr_managers_label(user):
    """Nhãn QL theo Nhân sự (có thể nhiều người)."""
    from hrm.permissions import format_direct_managers_label
    return format_direct_managers_label(user) or ''


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
