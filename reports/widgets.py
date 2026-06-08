from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class CKEditor5Widget(forms.Textarea):
    """CKEditor 5 (super-build CDN) — chỉ dùng form báo cáo office."""

    class Media:
        js = (
            'https://cdn.ckeditor.com/ckeditor5/43.3.1/super-build/ckeditor.js',
            'js/reports-office-ckeditor5.js',
        )

    def __init__(self, attrs=None):
        default_attrs = {'class': 'jp-ck5-source d-none'}
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
            '<div class="jp-ck5-editor" data-ck5-field="{}" data-ck5-textarea="{}">'
            '<div class="jp-ck5-chrome">'
            '<div class="jp-ck5-toolbar-host" id="ck5-toolbar-{}"></div>'
            '<div class="jp-ck5-paper">'
            '<div class="jp-ck5-editable-host" id="ck5-editable-{}"></div>'
            '</div>'
            '</div>'
            '{}'
            '</div>',
            name,
            field_id,
            field_id,
            field_id,
            textarea,
        ))
