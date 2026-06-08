from django import template

from PortalJustPlay.pagination import pagination_href, pagination_link_items

register = template.Library()


@register.simple_tag
def get_pagination_items(page_obj, window=2):
    try:
        window = int(window)
    except (TypeError, ValueError):
        window = 2
    return pagination_link_items(page_obj, window=max(1, window))


@register.simple_tag
def pagination_page_href(query_string, page_param, page_number):
    try:
        page_number = int(page_number)
    except (TypeError, ValueError):
        page_number = 1
    return pagination_href(query_string or '', page_param or 'page', page_number)
