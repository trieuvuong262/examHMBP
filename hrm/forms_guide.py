from django import forms
from django.utils.html import strip_tags
from ckeditor.widgets import CKEditorWidget

from hrm.models import UserGuide


class UserGuideTitleForm(forms.ModelForm):
    class Meta:
        model = UserGuide
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Tiêu đề trang hướng dẫn...',
            }),
        }


class UserGuideSectionForm(forms.Form):
    title = forms.CharField(
        label='Tiêu đề mục (hiển thị trên accordion)',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    body = forms.CharField(
        label='Nội dung mục',
        widget=CKEditorWidget(config_name='default'),
    )

    def clean_body(self):
        body = self.cleaned_data.get('body') or ''
        if not strip_tags(body).strip():
            raise forms.ValidationError('Nội dung mục không được để trống.')
        return body


class UserGuideForm(forms.ModelForm):
    """Giữ tương thích — không dùng cho luồng chỉnh sửa mới."""

    class Meta:
        model = UserGuide
        fields = ['title', 'subtitle', 'body']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tiêu đề trang hướng dẫn...',
            }),
            'subtitle': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Mô tả ngắn hiển thị dưới tiêu đề...',
            }),
        }

    def clean_body(self):
        body = self.cleaned_data.get('body') or ''
        if not strip_tags(body).strip():
            raise forms.ValidationError('Vui lòng nhập nội dung hướng dẫn.')
        return body
