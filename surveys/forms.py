from django import forms

from .models import Survey, SurveyResponse


class SurveyCreateForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('title', 'question', 'reference_url', 'required_course', 'deadline', 'is_active')
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
            'required_course': forms.Select(attrs={'class': 'form-select'}),
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
            'required_course': 'Bài học gợi ý (tuỳ chọn)',
            'deadline': 'Hạn nhận câu hỏi',
            'is_active': 'Đang mở nhận phản hồi',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deadline'].required = False
        self.fields['reference_url'].required = False
        self.fields['required_course'].required = False
        self.fields['deadline'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
        ]
        self.fields['required_course'].queryset = (
            self.fields['required_course'].queryset.filter(is_active=True).order_by('title')
        )
        self.fields['required_course'].empty_label = '— Không bắt buộc học trước —'


class SurveyReferenceForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = ('reference_url', 'required_course')
        widgets = {
            'reference_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://...',
            }),
            'required_course': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'reference_url': 'Link tham khảo / tài liệu',
            'required_course': 'Bài học gợi ý (tuỳ chọn)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['required_course'].required = False
        self.fields['required_course'].queryset = (
            self.fields['required_course'].queryset.filter(is_active=True).order_by('title')
        )
        self.fields['required_course'].empty_label = '— Không bắt buộc học trước —'


class SurveyResponseForm(forms.ModelForm):
    class Meta:
        model = SurveyResponse
        fields = ('answer',)
        widgets = {
            'answer': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Anh/chị vui lòng cân nhắc, đọc kỹ Sổ tay nhân viên và các văn bản quy định trước khi đặt câu hỏi. Nếu nội dung chưa rõ hoặc cần giải thích thêm, vui lòng ghi cụ thể nội dung cần được giải đáp',
            }),
        }
        labels = {
            'answer': 'Nhập câu hỏi',
        }
