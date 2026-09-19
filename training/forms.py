from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Course, Chapter, Lesson


def assigned_users_queryset(instance=None):
    """NV đang làm việc (+ người đã gán) để chọn vào khóa học."""
    from hrm.user_search import exclude_hidden_hrm_users

    employed = exclude_hidden_hrm_users(
        User.objects.filter(is_active=True, profile__is_employed=True),
    )
    qs = employed
    if instance is not None and getattr(instance, 'pk', None):
        qs = User.objects.filter(
            Q(pk__in=employed.values('pk')) | Q(pk__in=instance.assigned_users.values('pk')),
        )
    return qs.select_related(
        'profile',
        'profile__department',
        'profile__division',
    ).order_by('profile__full_name', 'username').distinct()


def assignee_quick_select_context():
    """Nhóm phòng ban / bộ phận / vị trí / vai trò cho chọn nhanh."""
    from hrm.models import Department, Division
    from hrm.permissions import ROLE_CHOICES
    from hrm.user_search import distinct_job_positions_for_filter

    departments = list(
        Department.objects.filter(is_active=True, profiles__is_employed=True)
        .distinct()
        .order_by('sort_order', 'name')
        .values('pk', 'name')
    )
    divisions = [
        {
            'pk': div.pk,
            'name': div.name,
            'department_name': div.department.name if div.department_id else '',
        }
        for div in (
            Division.objects.filter(is_active=True, division_profiles__is_employed=True)
            .select_related('department')
            .distinct()
            .order_by('department__sort_order', 'sort_order', 'name')
        )
    ]
    return {
        'quick_roles': ROLE_CHOICES,
        'quick_departments': departments,
        'quick_divisions': divisions,
        'quick_positions': distinct_job_positions_for_filter(),
    }


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
            'assigned_users': forms.CheckboxSelectMultiple(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'final_exam' in self.fields:
            from assessment.models import Exam

            self.fields['final_exam'].queryset = Exam.objects.filter(
                is_active=True, retry_of__isnull=True,
            ).order_by('-start_time', 'title')
            self.fields['final_exam'].required = False
            self.fields['final_exam'].empty_label = '— Không gắn bài thi —'
            self.fields['final_exam'].help_text = ''

        if 'assigned_users' in self.fields:
            self.fields['assigned_users'].queryset = assigned_users_queryset(self.instance)
            self.fields['assigned_users'].label_from_instance = self.get_user_label
            self.fields['assigned_users'].required = False

    def get_user_label(self, user):
        profile = getattr(user, 'profile', None)
        if profile:
            name = profile.full_name or user.get_full_name() or user.username
            pos = (profile.job_position or '').strip()
            return f'{name} ({pos})' if pos else name
        return user.username


class ChapterForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ['title', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: Chương 1: Tổng quan'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].required = False


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = [
            'title', 'lesson_type', 'content', 'video_url', 'video_file',
            'attachment', 'order', 'duration_estimate',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'lesson_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_lesson_type'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'video_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.youtube.com/watch?v=...',
            }),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'video/*'}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'duration_estimate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phút'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].required = False
        self.fields['duration_estimate'].required = False
        if not self.instance.pk:
            if not self.initial.get('duration_estimate'):
                self.initial['duration_estimate'] = 30
            if not self.initial.get('lesson_type'):
                self.initial['lesson_type'] = 'video'

    def clean(self):
        cleaned_data = super().clean()
        lesson_type = cleaned_data.get('lesson_type')
        video_url = cleaned_data.get('video_url')
        video_file = cleaned_data.get('video_file')
        attachment = cleaned_data.get('attachment')

        if lesson_type == 'video' and not video_url and not video_file:
            raise forms.ValidationError(
                'Video bài giảng cần link YouTube/Vimeo hoặc file video upload.'
            )

        if lesson_type == 'pdf' and not attachment:
            raise forms.ValidationError('Bài PDF cần tài liệu đính kèm.')

        return cleaned_data