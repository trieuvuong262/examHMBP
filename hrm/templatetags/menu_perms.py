from django import template

from hrm.menu_permissions import user_can_menu_action

register = template.Library()


@register.simple_tag(takes_context=True)
def jp_can_menu(context, module_key, menu_key, action='view'):
    request = context.get('request')
    if request is None or not request.user.is_authenticated:
        return False
    return user_can_menu_action(request.user, module_key, menu_key, action)
