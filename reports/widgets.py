from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class OfficeWordEditorWidget(forms.Textarea):
    """CKEditor 4 WordLike — ribbon đầy đủ, khởi tạo khi mở tab Văn bản."""

    def __init__(self, attrs=None):
        default_attrs = {'class': 'jp-word-textarea'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        final_attrs = self.build_attrs(attrs, extra_attrs={'name': name})
        field_id = final_attrs.get('id', f'id_{name}')
        final_attrs['id'] = field_id
        textarea = format_html(
            '<textarea{}>{}</textarea>',
            forms.widgets.flatatt(final_attrs),
            value or '',
        )
        return mark_safe(format_html(
            '<div class="jp-word-studio" data-word-textarea="{}">{}</div>',
            field_id,
            textarea,
        ))
