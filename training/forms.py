# training/forms.py
from django import forms
from django.contrib.auth.models import User  # <--- BẮT BUỘC THÊM DÒNG NÀY ĐỂ LẤY MODEL USER
from .models import Course, Chapter, Lesson

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
            
            # Dùng SelectMultiple và thêm class 'select2-user'
            'assigned_users': forms.SelectMultiple(attrs={'class': 'form-select select2-user'}),
            
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    # =========================================================================
    # 🎯 PHẦN THÊM MỚI: ÉP DJANGO IN RA "HỌ TÊN (CHỨC DANH)" TRONG THẺ OPTION
    # =========================================================================
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'assigned_users' in self.fields:
            # Tối ưu truy vấn (lấy luôn profile để khỏi bị query N+1)
            self.fields['assigned_users'].queryset = User.objects.select_related('profile').all()
            # Bắt Django dùng hàm get_user_label để in ra cái tên hiển thị
            self.fields['assigned_users'].label_from_instance = self.get_user_label

    def get_user_label(self, user):
        """Hàm biến đổi object User thành chuỗi text đẹp mắt"""
        # Nếu user có Profile
        if hasattr(user, 'profile'):
            # Lấy tên (ưu tiên full_name -> first_name -> username)
            name = user.profile.full_name or user.first_name or user.username
            # Lấy chức danh
            pos = user.profile.position or "Nhân viên"
            return f"{name} ({pos})"
        
        # Nếu user chưa có Profile thì đành lấy Username vậy
        return f"{user.username} (Nhân viên)"
    # =========================================================================


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