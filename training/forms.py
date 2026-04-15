
# training/forms.py
from django import forms
from .models import Course

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'category', 'description', 'thumbnail', 'final_exam', 'assigned_users', 'is_active']
        
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nhập tên khóa học...'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Mô tả ngắn gọn về khóa học...'}),
            'thumbnail': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'final_exam': forms.Select(attrs={'class': 'form-select'}),
            
            # SỬA DÒNG NÀY: Dùng SelectMultiple và thêm class 'select2-user'
            'assigned_users': forms.SelectMultiple(attrs={'class': 'form-select select2-user'}),
            
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }