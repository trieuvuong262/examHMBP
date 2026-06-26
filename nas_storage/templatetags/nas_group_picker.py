from django import template

register = template.Library()


def _selected_group_id(field, request):
    html_name = field.html_name
    if request and request.method == 'POST':
        val = request.POST.get(html_name)
        return [str(val)] if val else []

    value = field.value()
    if value is None:
        return []
    return [str(value)]


@register.inclusion_tag('includes/nas_group_picker.html', takes_context=True)
def nas_group_picker(
    context,
    field,
    groups=None,
    placeholder=None,
    picker_class='',
):
    if groups is None:
        groups = field.field.queryset

    request = context.get('request')
    selected_ids = _selected_group_id(field, request)

    if placeholder is None:
        placeholder = 'Chọn nhóm quyền NAS...'

    return {
        'field': field,
        'groups': groups,
        'selected_ids': selected_ids,
        'placeholder': placeholder,
        'picker_class': picker_class,
    }
