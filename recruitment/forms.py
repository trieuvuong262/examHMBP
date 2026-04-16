from django import forms
from .models import JobPosting

class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = ['title', 'department', 'position', 'quantity', 'deadline', 'is_active', 'description', 'requirements']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Bác sĩ Ngoại khoa'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'VD: Khoa Ngoại Tổng hợp'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Mô tả công việc...'}),
            'requirements': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Yêu cầu bằng cấp, kinh nghiệm...'}),
        }