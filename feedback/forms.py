from django import forms

from .models import Feedback


class FeedbackCreateForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ('title', 'category', 'body')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tóm tắt ngắn gọn'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Mô tả chi tiết góp ý của bạn...'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'category': 'Chủ đề',
            'body': 'Nội dung',
        }


class FeedbackReplyForm(forms.Form):
    body = forms.CharField(
        label='Nội dung phản hồi',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )


class FeedbackStatusForm(forms.Form):
    status = forms.ChoiceField(
        label='Trạng thái',
        choices=Feedback.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    body = forms.CharField(
        label='Phản hồi (tuỳ chọn)',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Gửi phản hồi cho người góp ý...'}),
    )
