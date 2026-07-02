from django import forms

from .models import Survey, SurveyResponse


class SurveyCreateForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('title', 'question', 'reference_url', 'deadline', 'is_active')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Giải đáp thắc mắc về Nội quy công ty',
            }),
            'question': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Nhập nội dung câu hỏi gửi nhân viên...',
            }),
            'reference_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://... (tuỳ chọn)',
            }),
            'deadline': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'class': 'form-control',
                    'type': 'datetime-local',
                },
            ),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Tiêu đề',
            'question': 'Nội dung câu hỏi',
            'reference_url': 'Link tham khảo',
            'deadline': 'Hạn nhận câu hỏi',
            'is_active': 'Đang mở nhận phản hồi',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].required = False
        self.fields['reference_url'].required = False
        self.fields['deadline'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]


class SurveyReferenceForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('reference_url',)
        widgets = {
            'reference_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://...',
            }),
        }
        labels = {
            'reference_url': 'Link tham khảo / tài liệu',
        }


class SurveyResponseForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = ('answer',)
        widgets = {
            'answer': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Ghi cụ thể nội dung cần được giải đáp (tuỳ chọn)...',
            }),
        }
        labels = {
            'answer': 'Nội dung câu hỏi',
        }
