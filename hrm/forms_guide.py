from django import forms
from django.utils.html import strip_tags

from hrm.models import UserGuide


class UserGuideForm(forms.ModelForm):
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
