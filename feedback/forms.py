from django import forms

from .models import Feedback


class FeedbackCreateForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ('title', 'body', 'is_anonymous')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tóm tắt ngắn gọn'}),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Mô tả chi tiết góp ý của bạn...',
            }),
            'is_anonymous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'body': 'Nội dung',
            'is_anonymous': 'Gửi ẩn danh',
        }
