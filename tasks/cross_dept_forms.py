from django import forms
from django.contrib.auth.models import User

from hrm.models import Department
from hrm.permissions import format_team_user_label

from .cross_dept_utils import get_department_task_users
from .models import InternalProject, WorkTask


class CrossDeptProjectForm(forms.ModelForm):
    departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by('sort_order', 'name'),
        label='Phòng ban tham gia',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
        help_text='Chọn ít nhất 2 phòng ban tham gia dự án.',
    )

    class Meta:
        model = InternalProject
        fields = ['title', 'description', 'due_date', 'departments']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_departments(self):
        departments = self.cleaned_data.get('departments')
        if not departments or departments.count() < 2:
            raise forms.ValidationError('Dự án liên phòng ban cần ít nhất 2 phòng ban tham gia.')
        return departments


class CrossDeptStepForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        label='Tên bước',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    description = forms.CharField(
        required=False,
        label='Mô tả',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    target_department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        label='Phòng ban xử lý',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    assignee_mode = forms.ChoiceField(
        choices=WorkTask.ASSIGNEE_MODE_CHOICES,
        initial=WorkTask.ASSIGNEE_DEPT_QUEUE,
        label='Cách gán người',
        widget=forms.Select(attrs={'class': 'form-select', 'data-jp-cross-dept-mode': '1'}),
    )
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label='Người phụ trách',
        widget=forms.Select(attrs={'class': 'form-select', 'data-jp-cross-dept-assignee': '1'}),
        help_text='Bắt buộc khi chọn «Chỉ định người».',
    )
    depends_on = forms.ModelChoiceField(
        queryset=WorkTask.objects.none(),
        required=False,
        label='Phụ thuộc bước (tuỳ chọn)',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Để trống nếu có thể làm song song với các bước khác.',
    )
    due_date = forms.DateField(
        required=False,
        label='Hạn bước',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    priority = forms.ChoiceField(
        choices=WorkTask.PRIORITY_CHOICES,
        initial=WorkTask.PRIORITY_NORMAL,
        label='Ưu tiên',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        if project is not None:
            self.fields['target_department'].queryset = project.departments.filter(
                is_active=True,
            ).order_by('sort_order', 'name')
            self.fields['depends_on'].queryset = project.steps.exclude(
                status__in={WorkTask.STATUS_CANCELLED, WorkTask.STATUS_HANDED_OFF},
            ).order_by('step_order', 'created_at')
            all_users = User.objects.none()
            for dept in project.departments.all():
                all_users = all_users | get_department_task_users(dept)
            self.fields['assignee'].queryset = all_users.distinct()
            self.fields['assignee'].label_from_instance = format_team_user_label

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('assignee_mode')
        assignee = cleaned.get('assignee')
        department = cleaned.get('target_department')
        project = self.project

        if project and department and not project.departments.filter(pk=department.pk).exists():
            self.add_error('target_department', 'Phòng ban không thuộc dự án này.')

        if mode == WorkTask.ASSIGNEE_SPECIFIC:
            if not assignee:
                self.add_error('assignee', 'Chọn người phụ trách khi gán trực tiếp.')
            elif department and assignee.profile.department_id != department.id:
                self.add_error('assignee', 'Người được chọn phải thuộc phòng ban xử lý.')
        elif mode == WorkTask.ASSIGNEE_DEPT_QUEUE:
            cleaned['assignee'] = None

        return cleaned
