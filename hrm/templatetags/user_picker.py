from django import template

register = template.Library()


def _selected_ids(field, mode, request):
    html_name = field.html_name
    if request and request.method == 'POST':
        if mode == 'single':
            val = request.POST.get(html_name)
            return [str(val)] if val else []
        return [str(v) for v in request.POST.getlist(html_name)]

    value = field.value()
    if value is None:
        return []
    if mode == 'single':
        return [str(value)]
    return [str(v) for v in value]


@register.inclusion_tag('includes/user_picker.html', takes_context=True)
def user_picker(
    context,
    field,
    mode=None,
    users=None,
    placeholder=None,
    show_bulk_actions=True,
    show_org_meta=False,
    picker_class='',
):
    if mode is None:
        mode = 'single' if field.field.__class__.__name__ == 'ModelChoiceField' else 'multiple'

    if users is None:
        users = field.field.queryset

    request = context.get('request')
    selected_ids = _selected_ids(field, mode, request)

    if placeholder is None:
        placeholder = 'Chọn nhân viên...' if mode == 'single' else 'Chọn một hoặc nhiều nhân viên...'

    return {
        'field': field,
        'users': users,
        'selected_ids': selected_ids,
        'mode': mode,
        'placeholder': placeholder,
        'show_bulk_actions': show_bulk_actions and mode == 'multiple',
        'show_org_meta': show_org_meta,
        'picker_class': picker_class,
    }
