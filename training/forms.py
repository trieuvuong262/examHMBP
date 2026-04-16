
# training/forms.py
from django import forms
from .models import Course
from .models import Chapter, Lesson

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
        

class ChapterForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ['title', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: Chương 1: Tổng quan'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['title', 'lesson_type', 'content', 'video_url', 'attachment', 'order', 'duration_estimate']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'lesson_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_lesson_type'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'video_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Link YouTube/Drive...'}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'duration_estimate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phút'}),
        }