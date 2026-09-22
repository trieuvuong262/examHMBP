from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def sx_team_work_nav(context):
    """Menu tổ = bộ phận HR phòng SẢN XUẤT + ĐẢM BẢO CHẤT LƯỢNG."""
    request = context.get('request')
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    from san_xuat.services.team_division_map import team_work_menu_items

    return team_work_menu_items(user)
