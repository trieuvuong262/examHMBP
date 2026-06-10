from django import template

register = template.Library()


@register.filter
def get_attr(obj, name):
    if isinstance(obj, dict):
        return obj.get(name, '')
    return getattr(obj, name, '')
