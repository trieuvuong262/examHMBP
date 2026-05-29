from django import forms

from .models import RequestType, ServiceRequest


class ServiceRequestCreateForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = ['title', 'description', 'estimated_cost']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: Đề xuất mua laptop cho nhân viên mới',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Mô tả chi tiết nhu cầu, cấu hình, lý do...',
            }),
            'estimated_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'VD: 15000000',
                'min': 0,
            }),
        }
        labels = {
            'title': 'Tiêu đề',
            'description': 'Nội dung yêu cầu',
            'estimated_cost': 'Dự toán chi phí (VNĐ)',
        }

    def __init__(self, *args, request_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_type = request_type
        self.fields['estimated_cost'].required = False

    def clean(self):
        cleaned = super().clean()
        if not self.request_type or not self.request_type.is_active:
            raise forms.ValidationError('Loại yêu cầu không khả dụng.')
        return cleaned


class StepActionForm(forms.Form):
    note = forms.CharField(
        required=False,
        label='Ghi chú / kết quả',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class RejectStepForm(forms.Form):
    reason = forms.CharField(
        required=True,
        label='Lý do từ chối',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
