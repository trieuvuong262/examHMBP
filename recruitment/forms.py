from django import forms
from .models import JobPosting

class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = ['title', 'department', 'position', 'quantity', 'deadline', 'is_active', 'description', 'requirements']
        
        # Đã thêm các class: bg-light, border-0, py-2, rounded-3 để ô nhập liệu nhìn hiện đại hơn
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'placeholder': 'VD: Bác sĩ Ngoại khoa'
            }),
            'department': forms.TextInput(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'placeholder': 'VD: Khoa Ngoại Tổng hợp'
            }),
            'position': forms.Select(attrs={
                'class': 'form-select bg-light border-0 py-2 rounded-3'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'min': 1
            }),
            'deadline': forms.DateInput(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input fs-5 border-secondary' # Phóng to nút check một chút
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'rows': 5, 
                'placeholder': 'Mô tả chi tiết công việc...'
            }),
            'requirements': forms.Textarea(attrs={
                'class': 'form-control bg-light border-0 py-2 rounded-3', 
                'rows': 5, 
                'placeholder': 'Yêu cầu bằng cấp, chứng chỉ hành nghề, kinh nghiệm...'
            }),
        }