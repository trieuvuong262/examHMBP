from django import template

# Bắt buộc phải có dòng này để khai báo biến register
register = template.Library()

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